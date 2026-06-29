"""
评估运行器 — LLM-as-Judge 实现 RAG 质量评估
参考 Ragas 设计：Faithfulness(拆陈述)、Context Precision(位置加权)、Answer Relevancy
使用 deepseek-v4-flash 降低成本，增量评估避免重复计算
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

from config import EVAL_MODEL
from models.db_models import get_session, EvaluationRecord
from evaluation.collector import collect_from_history
from services.kb_service import _parse_json
from services.llm_service import generate_json


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

请直接输出 JSON（不要用 markdown 代码块包裹）：
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

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{"points": ["要点1", "要点2"], "covered": [true, false], "score": 0.50, "reason": "2个要点中1个被覆盖"}}"""


CONTEXT_PRECISION_PROMPT = """你的任务是评估「检索文档」中每个片段是否与「用户问题」相关，同时关注**排名**——排在前面的相关片段价值更高。

## 用户问题
{question}

## 检索文档片段（按排名顺序，片段间以 --- 分隔）
{context}

## 评分步骤（必须严格按步骤执行）
1. 统计片段总数 N
2. 逐条判断每个片段是否与问题相关（true/false）
3. 按 Ragas 位置加权公式计算分数:
   - 对每个位置 k（从 1 开始），计算 Precision@k = (前 k 个位置中相关片段数 / k)
   - 只有第 k 个片段相关时，才累计 Precision@k
   - 最终分数 = 所有累计的 Precision@k 之和 / 总相关片段数

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{"relevant": [true, false, true], "score": 0.83, "reason": "3个片段中2个相关，第1个相关贡献1.0，第3个相关贡献0.67=(1+0.67)/2"}}"""


# ── 核心方法 ──────────────────────────────────────────────


def _score_with_llm(prompt: str) -> dict:
    """用 LLM 打分，返回完整的 JSON dict（含 claims/verdicts/relevant 等）"""
    try:
        raw = generate_json(
            [{"role": "user", "content": prompt}],
            temperature=0,
            model=EVAL_MODEL,  # 评估专用轻量模型
        )
        return json.loads(raw)
    except Exception as e:
        print(f"[Eval] LLM 评分失败: {e}")
        return {"score": 0}


def _build_context_block(contexts: list[str], max_chars: int = 3000) -> str:
    """拼接上下文，超长则截断"""
    if not contexts:
        return "（无检索文档）"
    block = "\n\n---\n\n".join(contexts)
    if len(block) > max_chars:
        block = block[:max_chars] + "\n\n... (内容过长已截断)"
    return block


def evaluate_single(question: str, answer: str, contexts: list[str]) -> dict:
    """对单条问答进行评估，三项指标并发调用 LLM"""
    context_block = _build_context_block(contexts)
    has_context = bool(contexts)

    tasks = OrderedDict([
        ("faithfulness", FAITHFULNESS_PROMPT.format(context=context_block, answer=answer)),
        ("answer_relevancy", ANSWER_RELEVANCY_PROMPT.format(question=question, answer=answer)),
        ("context_precision", CONTEXT_PRECISION_PROMPT.format(question=question, context=context_block)),
    ])

    results = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_score_with_llm, prompt): name for name, prompt in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                raw = future.result()
                results[name] = float(raw.get("score", 0))
            except Exception as e:
                print(f"[Eval] {name} 并发执行失败: {e}")
                results[name] = 0.0

    if not has_context:
        results["faithfulness"] = -1.0
        results["context_precision"] = -1.0

    return results


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

    if not dataset:
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
              f"新增评估 {len(new_items)} 条 (模型: {EVAL_MODEL})")

        total_start = time.time()
        results_by_idx = {}

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}
            for idx, d in new_items:
                future = pool.submit(evaluate_single, d["question"], d["answer"], d["contexts"])
                futures[future] = (idx, d)

            for future in as_completed(futures):
                idx, d = futures[future]
                has_ctx = bool(d.get("contexts"))
                try:
                    result = future.result()
                    results_by_idx[idx] = result
                    ctx_flag = "[CTX]" if has_ctx else "[NO_CTX]"
                    print(f"[Eval] {idx+1}/{len(dataset)} {ctx_flag}: "
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
        print(f"[Eval] 全部 {len(dataset)} 条已有评分，跳过评估")

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
    """从数据库加载已有评分 {metric_name: [score, ...]}"""
    session = get_session()
    try:
        records = session.query(EvaluationRecord)\
            .filter_by(kb_id=kb_id)\
            .filter(EvaluationRecord.faithfulness.isnot(None))\
            .all()
        scores = {"faithfulness": [], "answer_relevancy": [], "context_precision": []}
        for r in records:
            for key in scores:
                v = getattr(r, key, None)
                if v is not None and v >= 0:
                    scores[key].append(v)
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

            for key in ["faithfulness", "answer_relevancy", "context_precision"]:
                v = result.get(key, 0)
                if v >= 0:
                    setattr(record, key, float(v))
        session.commit()
        if created or updated:
            print(f"[Eval] 保存 {created} 新建 + {updated} 更新 到数据库")
    finally:
        session.close()
