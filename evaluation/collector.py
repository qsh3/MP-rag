"""
评估数据收集器 — 从聊天历史和评估记录中提取评估数据
"""
import json
from datetime import datetime

from models.db_models import get_session, ChatHistory, EvaluationRecord


def collect_from_history(kb_id: str, limit: int = 100) -> list[dict]:
    """从聊天历史 + 评估记录中收集问答数据（去重）

    Returns:
        [{"question": "...", "answer": "...", "contexts": [...], "ground_truth": ""}]
    """
    session = get_session()
    try:
        seen = set()
        dataset = []

        # 1. 从 ChatHistory 收集（主要来源）
        chats = session.query(ChatHistory)\
            .filter_by(kb_id=kb_id)\
            .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())\
            .limit(limit)\
            .all()

        for c in chats:
            key = c.question.strip()
            if key in seen:
                continue
            seen.add(key)
            contexts = _extract_contexts(c.sources)
            dataset.append({
                "question": c.question,
                "answer": c.answer,
                "contexts": contexts,
                "ground_truth": "",
            })

        # 2. 从 EvaluationRecord 收集（直接上传的测试数据，去重）
        records = session.query(EvaluationRecord)\
            .filter_by(kb_id=kb_id)\
            .order_by(EvaluationRecord.created_at.desc(), EvaluationRecord.id.desc())\
            .limit(limit)\
            .all()

        for r in records:
            key = r.question.strip()
            if key in seen:
                continue
            seen.add(key)
            ctx = _parse_json(r.contexts) if isinstance(r.contexts, str) else (r.contexts or [])
            dataset.append({
                "question": r.question,
                "answer": r.answer,
                "contexts": ctx,
                "ground_truth": r.ground_truth or "",
            })

        # 统计
        empty_ctx = sum(1 for d in dataset if not d["contexts"])
        empty_ans = sum(1 for d in dataset if not d["answer"])
        print(f"[Collector] kb={kb_id}: 共 {len(dataset)} 条 (ChatHistory={len(chats)}, EvalRecord={len(records)})")
        if empty_ctx:
            print(f"[Collector] WARN: {empty_ctx}/{len(dataset)} 条无检索上下文（RAGFlow 检索可能异常）")
        if empty_ans:
            print(f"[Collector] WARN: {empty_ans}/{len(dataset)} 条无答案")

        return dataset
    finally:
        session.close()


def _extract_contexts(sources_raw) -> list[str]:
    """从 ChatHistory.sources JSON 中提取文档片段文本"""
    sources = _parse_json(sources_raw)
    contexts = []
    for s in sources:
        # 依次尝试多个字段获取内容
        chunk = (
            s.get("chunk_text") or
            s.get("content") or
            s.get("text") or
            ""
        )
        if chunk and chunk not in contexts:
            contexts.append(chunk)
    return contexts


def get_evaluated_scores(kb_id: str, limit: int = 100) -> list[dict]:
    """获取已有评分的评估记录（去重：同问题只保留最新一条）"""
    session = get_session()
    try:
        records = session.query(EvaluationRecord)\
            .filter_by(kb_id=kb_id)\
            .filter(EvaluationRecord.faithfulness.isnot(None))\
            .order_by(EvaluationRecord.created_at.desc(), EvaluationRecord.id.desc())\
            .limit(limit * 3)\
            .all()

        # 去重：同问题只保留最新一条
        seen = set()
        deduped = []
        for r in records:
            key = r.question.strip() if r.question else ""
            if key in seen:
                continue
            seen.add(key)
            deduped.append({
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "faithfulness": r.faithfulness,
                "answer_relevancy": r.answer_relevancy,
                "context_precision": r.context_precision,
                "context_recall": r.context_recall,
                "created_at": r.created_at or "",
            })

        return deduped[:limit]
    finally:
        session.close()


def get_pending_records(kb_id: str) -> list[dict]:
    """获取尚未评估的记录"""
    session = get_session()
    try:
        records = session.query(EvaluationRecord)\
            .filter_by(kb_id=kb_id)\
            .filter(EvaluationRecord.faithfulness == None)\
            .all()

        return [
            {
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "contexts": _parse_json(r.contexts) if isinstance(r.contexts, str) else (r.contexts or []),
                "ground_truth": r.ground_truth,
            }
            for r in records
        ]
    finally:
        session.close()


def _parse_json(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return []
