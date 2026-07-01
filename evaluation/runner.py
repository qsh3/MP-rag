"""
评估运行器 — LLM-as-Judge 实现 RAG 质量评估
参考 Ragas 设计：Faithfulness(拆陈述)、Context Precision(位置加权)、Answer Relevancy
使用 deepseek-v4-flash 降低成本，增量评估避免重复计算
"""
import json
import re
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

from config import EVAL_MODEL, REVIEW_MODEL, DASHSCOPE_API_KEY
from models.db_models import get_session, EvaluationRecord
from evaluation.collector import collect_from_history
from services.kb_service import _parse_json
from services.llm_service import generate_json

# 信号量控制全局 API 并发，防厂商限流
# Kimi 组织级别并发上限 = 3，与 key 数量无关
_kimi_semaphore = threading.Semaphore(3)
_dashscope_semaphore = threading.Semaphore(10)  # DashScope 防骤升触发限流


# ── 评估 Prompt（对齐 Ragas 计算原理）────────────────────

FAITHFULNESS_PROMPT = """你的任务是评估「答案」中的事实性声明是否能从「检索文档」中找到依据。

## 检索文档
{context}

## 答案
{answer}

## 评分步骤（必须严格按步骤执行）
1. 将「答案」逐条拆解为独立的事实性声明/断言（编号 1, 2, 3...）
2. 逐条判断每一条声明是否能从「检索文档」中找到明确依据
   - true = 文档中明确包含相同或等价的信息
   - false = 文档中找不到或与文档内容矛盾
3. 计算分数: 有依据的声明数 / 总声明数（0.0–1.0）

请直接输出 JSON，不要用 markdown 代码块包裹。reason 应尽可能简短，不得超过1000字：
{{"claims": ["声明1", "声明2"], "verdicts": [true, false], "score": 0.50, "reason": "2条声明中1条有依据"}}"""


ANSWER_RELEVANCY_PROMPT = """你的任务是评估「答案」是否直接、完整地回答了「用户问题」。

## 用户问题
{question}

## 答案
{answer}

## 评分步骤（必须严格按步骤执行）
1. 分析「用户问题」中包含几个关键要点/子问题（编号 1, 2, 3...）
2. 逐条检查「答案」是否覆盖了每一个要点
   - true = 答案中明确回答了该要点
   - false = 答案中遗漏或未涉及该要点
3. 计算分数: 已覆盖的要点数 / 总要点数（0.0–1.0）

请直接输出 JSON，不要用 markdown 代码块包裹。reason 应尽可能简短，不得超过1000字：
{{"points": ["要点1", "要点2"], "covered": [true, false], "score": 0.50, "reason": "2个要点中1个被覆盖"}}"""


CONTEXT_PRECISION_PROMPT = """判断以下检索片段是否与问题相关，关注排名——靠前的相关片段价值更高。

## 用户问题
{question}

## 检索片段（按排名，每个片段截取前 300 字）
{context}

## 步骤
1. 对每个片段判断是否与问题相关（true/false）
2. 按位置加权公式计分：仅当第 k 个片段相关时累计 Precision@k = 前k个相关数/k，最终分 = 累计值/总相关数

直接输出 JSON，不要用 markdown 代码块包裹。reason 应尽可能简短，不得超过1000字：
{{"relevant": [true, false, true], "score": 0.83, "reason": "..."}}"""


REVIEW_FAITHFULNESS_PROMPT = """你的任务是对另一名 LLM 评估者的「忠实度」评分进行复审。请判断评估者的打分是否合理，必要时做出调整。

## 原始问题
{question}

## 答案
{answer}

## 评估者的 Faithfulness 评分与推理
- 分数: {score}
- 拆解的声明: {claims}
- 逐条判定: {verdicts}
- 理由: {reason}

## 复审步骤
1. 逐条检查评估者的声明拆解和判定是否准确、有无遗漏
2. 判断分数是否合理（0.0-1.0）
3. 如果需要调整，给出调整后的分数和理由

## 调整规则
- 调整幅度 <= 0.1 时，以原分为准
- 调整幅度 > 0.1 时，以复审者调整分为准

请直接输出 JSON。reason 应尽可能简短，不得超过1000字：{{"adjusted_score": 0.80, "reason": "..."}}"""

REVIEW_ANSWER_RELEVANCY_PROMPT = """你的任务是对另一名 LLM 评估者的「答案相关性」评分进行复审。请判断评估者的打分是否合理，必要时做出调整。

## 原始问题
{question}

## 答案
{answer}

## 评估者的 Answer Relevancy 评分与推理
- 分数: {score}
- 问题要点: {points}
- 覆盖判定: {covered}
- 理由: {reason}

## 复审步骤
1. 逐条检查评估者的要点拆解和覆盖判定是否准确
2. 判断分数是否合理（0.0-1.0）
3. 如果需要调整，给出调整后的分数和理由

## 调整规则
- 调整幅度 <= 0.1 时，以原分为准
- 调整幅度 > 0.1 时，以复审者调整分为准

请直接输出 JSON。reason 应尽可能简短，不得超过1000字：{{"adjusted_score": 0.90, "reason": "..."}}"""

REVIEW_CONTEXT_PRECISION_PROMPT = """你的任务是对另一名 LLM 评估者的「上下文精度」评分进行复审。请判断评估者的打分是否合理，必要时做出调整。

## 原始问题
{question}

## 答案
{answer}

## 评估者的 Context Precision 评分与推理
- 分数: {score}
- 片段相关判定: {relevant}
- 理由: {reason}

## 复审步骤
1. 逐条检查评估者的片段相关性判定是否准确
2. 判断分数是否合理（0.0-1.0）
3. 如果需要调整，给出调整后的分数和理由

## 调整规则
- 调整幅度 <= 0.1 时，以原分为准
- 调整幅度 > 0.1 时，以复审者调整分为准

请直接输出 JSON。reason 应尽可能简短，不得超过1000字：{{"adjusted_score": 0.75, "reason": "..."}}"""


# ── 核心方法 ──────────────────────────────────────────────


def _score_with_llm(prompt: str, label: str = "") -> dict:
    """用 LLM 打分"""
    tag = f"[Eval:{label}]" if label else "[Eval]"
    try:
        with _dashscope_semaphore:
            raw = generate_json(
                [{"role": "user", "content": prompt}],
                temperature=0,
                model=EVAL_MODEL,
                provider="dashscope",
            )
        return json.loads(raw)
    except Exception as e:
        print(f"{tag} 失败: {e}", flush=True)
        return {"score": 0}


def _build_context_block(contexts: list[str], max_chars: int = 3000,
                         per_chunk_chars: int = 0) -> str:
    """拼接上下文，超长则截断

    Args:
        per_chunk_chars: 每个片段保留的前N字（0=不截断单片段）
    """
    if not contexts:
        return "（无检索文档）"
    chunks = contexts
    if per_chunk_chars > 0:
        chunks = [c[:per_chunk_chars] + ("..." if len(c) > per_chunk_chars else "") for c in contexts]
    block = "\n\n---\n\n".join(chunks)
    if len(block) > max_chars:
        block = block[:max_chars] + "\n\n... (内容过长已截断)"
    return block


def evaluate_single(question: str, answer: str, contexts: list[str],
                    label: str = "") -> dict:
    """对单条问答进行三项指标并发评估（不含复审）

    Returns:
        {
            "faithfulness": 0.8,           # 评估分数
            "answer_relevancy": 0.9,
            "context_precision": 0.75,
            "_raw_eval": {...},              # 评估者完整推理（写入数据库供复审使用）
        }
    """
    tag = f"[Eval{':'+label if label else ''}]"
    context_block = _build_context_block(contexts)
    context_short = _build_context_block(contexts, max_chars=2000, per_chunk_chars=300)
    has_context = bool(contexts)

    tasks = OrderedDict([
        ("faithfulness", FAITHFULNESS_PROMPT.format(context=context_block, answer=answer)),
        ("answer_relevancy", ANSWER_RELEVANCY_PROMPT.format(question=question, answer=answer)),
        ("context_precision", CONTEXT_PRECISION_PROMPT.format(question=question, context=context_short)),
    ])

    raw_results = {}
    results = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_score_with_llm, prompt, f"{label}/{name}" if label else name): name
                   for name, prompt in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                raw = future.result()
                raw_results[name] = raw
                results[name] = float(raw.get("score", 0))
            except Exception as e:
                print(f"[Eval] {name} 并发执行失败: {e}", flush=True)
                raw_results[name] = {"score": 0}
                results[name] = 0.0

    if not has_context:
        results["faithfulness"] = -1.0
        results["context_precision"] = -1.0
        raw_results["faithfulness"] = {"score": -1}
        raw_results["context_precision"] = {"score": -1}

    results["_raw_eval"] = raw_results
    return results


def _review_single_metric(prompt: str, metric_name: str) -> dict:
    """复审单项指标（信号量 + 随机抖动防组织限流）"""
    try:
        time.sleep(random.uniform(0.3, 1.5))  # 随机抖动，避免请求扎堆触发组织限流
        with _kimi_semaphore:
            raw = generate_json(
                [{"role": "user", "content": prompt}],
                temperature=1,  # kimi-k2.5 只支持 temperature=1
                model=REVIEW_MODEL,
                provider="kimi",
            )
        return json.loads(raw)
    except Exception as e:
        print(f"[Review] {metric_name} 失败: {e}", flush=True)
        return {"adjusted_score": None, "reason": str(e)}


def _adjust_if_needed(original: float, adjusted: float | None, metric_name: str) -> tuple[float, str | None]:
    """判断是否需要采纳复审调整：幅度 > 0.1 才采纳"""
    if adjusted is None:
        return original, None
    if abs(adjusted - original) > 0.1:
        return adjusted, f"{metric_name}: {original:.2f}→{adjusted:.2f}"
    return original, None


# ── 独立复审入口 ──────────────────────────────────────────


def review_single(question: str, answer: str, contexts: list[str],
                  eval_raw: dict) -> dict:
    """对已评估的单条记录进行三项指标并发复审

    Returns:
        {"review_scores": {...}, "review_reason": "...", "changes": [...], "_raw_review": {...}}
    """
    defaults = {k: float(eval_raw.get(k, {}).get("score", 0))
                for k in ["faithfulness", "answer_relevancy", "context_precision"]}

    if not DASHSCOPE_API_KEY:
        return {"review_scores": defaults, "review_reason": "DASHSCOPE_API_KEY 未配置", "changes": [], "_raw_review": {}}

    # 构建三个独立 prompt（复审只看问答+评估结果，不传检索文档，避免上下文过长）
    faith = eval_raw.get("faithfulness", {})
    relev = eval_raw.get("answer_relevancy", {})
    prec = eval_raw.get("context_precision", {})

    tasks = OrderedDict([
        ("faithfulness", REVIEW_FAITHFULNESS_PROMPT.format(
            question=question, answer=answer,
            score=faith.get("score", 0),
            claims=json.dumps(faith.get("claims", []), ensure_ascii=False),
            verdicts=json.dumps(faith.get("verdicts", []), ensure_ascii=False),
            reason=faith.get("reason", ""),
        )),
        ("answer_relevancy", REVIEW_ANSWER_RELEVANCY_PROMPT.format(
            question=question, answer=answer,
            score=relev.get("score", 0),
            points=json.dumps(relev.get("points", []), ensure_ascii=False),
            covered=json.dumps(relev.get("covered", []), ensure_ascii=False),
            reason=relev.get("reason", ""),
        )),
        ("context_precision", REVIEW_CONTEXT_PRECISION_PROMPT.format(
            question=question, answer=answer,
            score=prec.get("score", 0),
            relevant=json.dumps(prec.get("relevant", []), ensure_ascii=False),
            reason=prec.get("reason", ""),
        )),
    ])

    # 三项并发复审
    raw_review = {}
    review_scores = {}
    changes = []
    reasons = []

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_review_single_metric, prompt, name): name
                   for name, prompt in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                raw_review[name] = result
                original = defaults[name]
                adjusted = result.get("adjusted_score")
                final, change = _adjust_if_needed(original, adjusted, name)
                review_scores[name] = final
                if change:
                    changes.append(change)
                reasons.append(f"{name}: {result.get('reason', '')}")
            except Exception as e:
                print(f"[Review] {name} 并发复审失败: {e}")
                raw_review[name] = {"error": str(e)}
                review_scores[name] = defaults[name]

    return {
        "review_scores": review_scores,
        "review_reason": "; ".join(reasons) if reasons else "",
        "changes": changes,
        "_raw_review": raw_review,
    }


def run_review(kb_id: str, max_samples: int = 10) -> dict:
    """对已评估但未复审的记录进行批量复审

    Args:
        kb_id: 知识库 ID
        max_samples: 最大复审样本数

    Returns:
        {"kb_id": ..., "reviewed_count": N, "metrics": [...], "review": {...}}
    """
    session = get_session()
    try:
        # 加载已评估但未复审的记录（reviewed=0，faithfulness 不为 NULL）
        records = session.query(EvaluationRecord)\
            .filter_by(kb_id=kb_id)\
            .filter(EvaluationRecord.faithfulness.isnot(None))\
            .filter(EvaluationRecord.reviewed == 0)\
            .all()

        if not records:
            print("[Review] 没有待复审的记录（所有已评估记录均已复审或不可复审）")
            return {
                "kb_id": kb_id,
                "reviewed_count": 0,
                "metrics": [],
                "review": None,
                "error": "没有待复审的记录，请先运行评估",
            }

        # 限制数量
        if len(records) > max_samples:
            records = records[:max_samples]

        print(f"[Review] 待复审 {len(records)} 条 (模型: {REVIEW_MODEL}, 厂商: dashscope)")

        total_start = time.time()
        results_by_id = {}

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}
            for r in records:
                eval_raw = _parse_json(r.eval_raw) if r.eval_raw else {}
                # 如果 eval_raw 为空（旧记录），用 DB 中保存的分数构造最小 eval_raw
                if not eval_raw:
                    eval_raw = {
                        "faithfulness": {"score": r.faithfulness or 0},
                        "answer_relevancy": {"score": r.answer_relevancy or 0},
                        "context_precision": {"score": r.context_precision or 0},
                    }
                contexts = _parse_json(r.contexts)
                future = pool.submit(
                    review_single, r.question, r.answer, contexts, eval_raw
                )
                futures[future] = r.id

            for future in as_completed(futures):
                rid = futures[future]
                try:
                    review_result = future.result()
                    results_by_id[rid] = review_result
                    changes = review_result.get("changes", [])
                    print(f"[Review] {rid}: "
                          f"faith={review_result['review_scores'].get('faithfulness', 0):.2f} "
                          f"relev={review_result['review_scores'].get('answer_relevancy', 0):.2f} "
                          f"prec={review_result['review_scores'].get('context_precision', 0):.2f}"
                          + (f"  调整: {', '.join(changes)}" if changes else ""))
                except Exception as e:
                    print(f"[Review] {rid} 复审失败: {e}")
                    results_by_id[rid] = {
                        "review_scores": {},
                        "review_reason": f"复审失败: {e}",
                        "changes": [],
                        "_raw_review": {},
                    }

        # 保存复审结果
        _save_review_results(records, results_by_id)

        total_elapsed = time.time() - total_start
        print(f"[Review] 复审完成: {len(results_by_id)} 条，耗时 {total_elapsed:.1f}s")

        # 汇总复审后指标
        all_scores = _load_existing_scores(kb_id)
        eval_metrics = _aggregate_metrics(all_scores)

        review_summary = None
        if all_scores.get("review_faithfulness"):
            review_summary = {
                "reviewed_count": len(all_scores.get("review_faithfulness", [])),
                "avg_review_scores": {
                    "faithfulness": round(sum(all_scores["review_faithfulness"]) / len(all_scores["review_faithfulness"]), 4),
                    "answer_relevancy": round(sum(all_scores["review_answer_relevancy"]) / len(all_scores["review_answer_relevancy"]), 4),
                    "context_precision": round(sum(all_scores["review_context_precision"]) / len(all_scores["review_context_precision"]), 4),
                },
            }

        return {
            "kb_id": kb_id,
            "reviewed_count": len(results_by_id),
            "metrics": eval_metrics,
            "review": review_summary,
        }

    except Exception as e:
        print(f"[Review] 批量复审异常: {e}")
        return {"kb_id": kb_id, "reviewed_count": 0, "metrics": [], "review": None, "error": str(e)}
    finally:
        session.close()


def _save_review_results(records: list, results: dict):
    """将复审结果写入数据库"""
    session = get_session()
    try:
        updated = 0
        for r in records:
            if r.id not in results:
                continue
            review_result = results[r.id]
            if review_result.get("review_reason", "").startswith("DASHSCOPE_API_KEY 未配置"):
                continue

            # 将原 session 已关闭的 detached 对象合并到当前 session
            r = session.merge(r)
            r.reviewed = 1
            review_scores = review_result.get("review_scores", {})
            for key in ["faithfulness", "answer_relevancy", "context_precision"]:
                rv = review_scores.get(key)
                if rv is not None:
                    setattr(r, f"review_{key}", float(rv))
            r.review_reason = review_result.get("review_reason", "")
            r.review_changes = json.dumps(review_result.get("changes", []), ensure_ascii=False)
            r.review_raw = json.dumps(review_result.get("_raw_review", {}), ensure_ascii=False)
            updated += 1

        session.commit()
        if updated:
            print(f"[Review] 保存 {updated} 条复审结果到数据库")
    finally:
        session.close()


# ── 批量评估入口 ──────────────────────────────────────────


def run_ragas_evaluation(kb_id: str, test_questions: list[str] = None,
                         max_samples: int = 10) -> dict:
    """运行 RAG 评估（增量：已有评分的跳过）

    Args:
        kb_id: 知识库 ID
        test_questions: 可选指定测试问题
        max_samples: 新评估的最大样本数

    Returns:
        {"kb_id": ..., "sample_count": N, "metrics": [...], "new_evaluated": N}
    """
    if test_questions:
        session = get_session()
        try:
            records = session.query(EvaluationRecord)\
                .filter_by(kb_id=kb_id)\
                .filter(EvaluationRecord.question.in_(test_questions))\
                .all()
            dataset = [{"question": r.question, "answer": r.answer,
                        "contexts": _parse_json(r.contexts),
                        "ground_truth": r.ground_truth or ""} for r in records]
        finally:
            session.close()
    else:
        dataset = collect_from_history(kb_id)

    print(f"[Eval] KB={kb_id}: 采集到 {len(dataset)} 条待评估数据", flush=True)
    if not dataset:
        print("[Eval] 无数据！请先在问答页面进行对话，或通过 test_questions 指定测试问题", flush=True)
        return {
            "kb_id": kb_id,
            "sample_count": 0,
            "metrics": [],
            "error": "没有可用的评估数据，请先进行一些问答操作",
        }

    # ── 增量评估：跳过已有评分的条目 ──
    evaluated_questions = _get_evaluated_questions(kb_id)
    new_items = []
    for i, d in enumerate(dataset):
        key = d["question"].strip()
        if key in evaluated_questions:
            continue  # 已有评分，跳过
        if not d.get("answer", "").strip():
            continue  # 无答案，跳过
        new_items.append((i, d))

    if new_items:
        # 限制新增评估数量
        if len(new_items) > max_samples:
            new_items = new_items[:max_samples]

        print(f"[Eval] {len(dataset)} 条中 {len(evaluated_questions)} 条已评分，"
              f"新增评估 {len(new_items)} 条 (模型: {EVAL_MODEL})", flush=True)

        total_start = time.time()
        results_by_idx = {}

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}
            for idx, d in new_items:
                future = pool.submit(evaluate_single, d["question"], d["answer"], d["contexts"], str(idx+1))
                futures[future] = (idx, d)

            for future in as_completed(futures):
                idx, d = futures[future]
                has_ctx = bool(d.get("contexts"))
                try:
                    result = future.result()
                    results_by_idx[idx] = result
                    print(f"[Eval] {idx+1}/{len(dataset)}: "
                          f"faith={result['faithfulness']:.2f} "
                          f"relev={result['answer_relevancy']:.2f} "
                          f"prec={result['context_precision']:.2f}")
                except Exception as e:
                    print(f"[Eval] 第 {idx+1} 条评估失败: {e}")
                    results_by_idx[idx] = {"faithfulness": 0, "answer_relevancy": 0, "context_precision": 0}

        # 保存新评分
        _save_scores(kb_id, dataset, results_by_idx)
        total_elapsed = time.time() - total_start
        print(f"[Eval] 新增评估完成: {len(results_by_idx)} 条，耗时 {total_elapsed:.1f}s")
    else:
        print(f"[Eval] 数据集 {len(dataset)} 条，但无可评估的新条目", flush=True)
        print(f"[Eval] 已评分: {len(evaluated_questions)} 条, 无答案: {sum(1 for d in dataset if not d.get('answer', '').strip())} 条", flush=True)

    # ── 汇总所有评分（已有 + 新增） ──
    all_scores = _load_existing_scores(kb_id)
    eval_metrics = _aggregate_metrics(all_scores)

    # 从 all_scores 计算出 sample_count
    if all_scores:
        sample_count = max(len(all_scores.get(k, [])) for k in ["faithfulness", "answer_relevancy", "context_precision"])
    else:
        sample_count = 0

    print(f"[Eval] 汇总: {sample_count} 条 | "
          f"faith={eval_metrics[0]['score']:.3f} "
          f"relev={eval_metrics[1]['score']:.3f} "
          f"prec={eval_metrics[2]['score']:.3f}")

    return {
        "kb_id": kb_id,
        "sample_count": sample_count,
        "metrics": eval_metrics,
        "new_evaluated": len(new_items),
    }


def _get_evaluated_questions(kb_id: str) -> set:
    """获取已有评分的题目集合（用于增量跳过）"""
    session = get_session()
    try:
        records = session.query(EvaluationRecord.question)\
            .filter_by(kb_id=kb_id)\
            .filter(EvaluationRecord.faithfulness.isnot(None))\
            .all()
        return {r.question.strip() for r in records if r.question}
    finally:
        session.close()


def _load_existing_scores(kb_id: str) -> dict:
    """从数据库加载已有评分 {metric_name: [score, ...]}（含复审分数）"""
    session = get_session()
    try:
        records = session.query(EvaluationRecord)\
            .filter_by(kb_id=kb_id)\
            .filter(EvaluationRecord.faithfulness.isnot(None))\
            .all()
        scores = {
            "faithfulness": [], "answer_relevancy": [], "context_precision": [],
            "review_faithfulness": [], "review_answer_relevancy": [], "review_context_precision": [],
        }
        for r in records:
            for key in ["faithfulness", "answer_relevancy", "context_precision"]:
                v = getattr(r, key, None)
                if v is not None and v >= 0:
                    scores[key].append(v)
            # 加载复审分数
            for key in ["faithfulness", "answer_relevancy", "context_precision"]:
                rv = getattr(r, f"review_{key}", None)
                if rv is not None and rv >= 0:
                    scores[f"review_{key}"].append(rv)
        return scores
    finally:
        session.close()


def _aggregate_metrics(all_scores: dict) -> list[dict]:
    """聚合评分为前端格式"""
    descriptions = {
        "faithfulness": "答案中的断言是否可追溯到检索文档（0-1，越高越好）",
        "answer_relevancy": "答案是否直接回答了问题、不偏题（0-1，越高越好）",
        "context_precision": "检索文档的相关性与排名质量（位置加权，0-1，越高越好）",
        "context_recall": "是否检索到了所有必要信息（0-1，越高越好）",
    }
    metrics = []
    for name in ["faithfulness", "answer_relevancy", "context_precision"]:
        vals = [v for v in all_scores.get(name, []) if v >= 0]
        if vals:
            avg = round(sum(vals) / len(vals), 4)
        else:
            avg = 0
        metrics.append({"name": name, "score": avg, "description": descriptions.get(name, "")})
    return metrics


def _save_scores(kb_id: str, dataset: list[dict], results: dict):
    """保存新评分到数据库（防重复：写入前清掉同问题的旧记录，保留最新）

    Args:
        results: {dataset_index: {"faithfulness": 0.8, ...}}
    """
    session = get_session()
    try:
        updated = 0
        created = 0
        for i, d in enumerate(dataset):
            if i not in results:
                continue
            result = results[i]
            q = d["question"].strip()

            # 删掉同问题的旧记录（无论有没有评分），避免重复堆积
            old = session.query(EvaluationRecord)\
                .filter_by(kb_id=kb_id)\
                .filter(EvaluationRecord.question == q)\
                .all()
            if len(old) > 1:
                # 保留最早的 id，删掉其余的
                for r in old[1:]:
                    session.delete(r)
                record = old[0]
            elif len(old) == 1:
                record = old[0]
            else:
                record = None

            if not record:
                from models.db_models import gen_id
                record = EvaluationRecord(
                    id=gen_id(),
                    kb_id=kb_id,
                    question=q,
                    answer=d["answer"],
                    contexts=json.dumps(d.get("contexts", []), ensure_ascii=False),
                    ground_truth=d.get("ground_truth", ""),
                )
                session.add(record)
                session.flush()
                created += 1
            else:
                updated += 1

            # 保存评估者分数和原始推理
            for key in ["faithfulness", "answer_relevancy", "context_precision"]:
                v = result.get(key, 0)
                if v >= 0:
                    setattr(record, key, float(v))
            if result.get("_raw_eval"):
                record.eval_raw = json.dumps(result.get("_raw_eval", {}), ensure_ascii=False)

        session.commit()
        if created or updated:
            print(f"[Eval] 保存 {created} 新建 + {updated} 更新 到数据库")
    finally:
        session.close()
