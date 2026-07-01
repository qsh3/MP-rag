"""
问答服务 — RAGFlow 检索 + DeepSeek 生成
"""
import json

from rag_client import get_client as get_rag_client
from services.llm_service import generate_rag_stream, generate, RAG_SYSTEM_PROMPT
from services.kb_service import save_chat, save_evaluation_record


def _build_context(search_results: list[dict]) -> tuple[str, list[dict]]:
    """构建 LLM 上下文和来源列表

    Returns:
        (context_text, sources) — context 是拼接好的文本，sources 是结构化来源信息
    """
    sources = []
    context_parts = []

    for i, r in enumerate(search_results):
        doc_name = r.get("doc_name", "未知文档")
        content = r.get("content", "")
        score = r.get("score", 0)

        context_parts.append(f"[文档{i+1}: {doc_name}] (相关度: {score:.2f})\n{content}")
        sources.append({
            "doc_name": doc_name,
            "doc_id": r.get("doc_id", ""),
            "chunk_text": content[:300],
            "score": score,
        })

    return "\n\n---\n\n".join(context_parts), sources


def ask_stream(kb_id: str, question: str, top_k: int = 5, session_id: str = None):
    """流式问答（同步生成器，由 FastAPI StreamingResponse 驱动）

    Yields:
        SSE 格式的 dict: {"event": "sources"|"token"|"done"|"error", "data": ...}
    """
    rag = get_rag_client()
    dataset_id = None

    # 0. 加载历史对话上下文
    history_context = ""
    if session_id:
        from services.kb_service import get_session_history
        history = get_session_history(kb_id, session_id)
        if history:
            parts = []
            for h in history[-6:]:  # 最近 6 轮对话
                parts.append(f"用户: {h['question']}\n助手: {h['answer']}")
            history_context = "\n\n".join(parts)

    # 1. 获取 RAGFlow dataset_id
    from services.kb_service import get_kb
    kb = get_kb(kb_id)
    if kb:
        dataset_id = kb.get("ragflow_dataset_id")

    # 2. RAGFlow 混合检索（服务端自动停用词过滤 + 词权重 + 同义扩展）
    if not dataset_id and not rag.available:
        search_results = rag._local_search(question, top_k)
    else:
        search_results = rag.search(dataset_id, question, top_k)

    # 3. 构建上下文
    context, sources = _build_context(search_results)

    # 4. 流式生成
    yield {"event": "sources", "data": json.dumps(sources, ensure_ascii=False)}

    full_answer = []
    try:
        for token in generate_rag_stream(context, question, history_context):
            full_answer.append(token)
            yield {"event": "token", "data": token}
    except Exception as e:
        yield {"event": "error", "data": str(e)}
        return

    answer = "".join(full_answer)

    # 5. 保存聊天记录
    save_chat(kb_id, question, answer, sources, session_id)

    # 6. 保存评估记录
    save_evaluation_record(
        kb_id=kb_id,
        question=question,
        answer=answer,
        contexts=[s["chunk_text"] for s in sources],
    )

    yield {"event": "done", "data": json.dumps({"sources": sources, "session_id": session_id}, ensure_ascii=False)}


def ask_sync(kb_id: str, question: str, top_k: int = 5) -> dict:
    """非流式问答（一次性返回）"""
    rag = get_rag_client()

    from services.kb_service import get_kb
    kb = get_kb(kb_id)
    dataset_id = kb.get("ragflow_dataset_id") if kb else None

    # RAGFlow 混合检索
    if dataset_id or rag.available:
        search_results = rag.search(dataset_id, question, top_k)
    else:
        search_results = rag._local_search(question, top_k)

    # 构建上下文
    context, sources = _build_context(search_results)

    user_prompt = f"## 参考文档\n\n{context}\n\n## 用户问题\n\n{question}\n\n请根据参考文档回答用户问题。"
    answer = generate(
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        stream=False,
    )

    # 保存记录
    save_chat(kb_id, question, answer, sources)
    save_evaluation_record(
        kb_id=kb_id, question=question, answer=answer,
        contexts=[s["chunk_text"] for s in sources],
    )

    return {
        "answer": answer,
        "sources": sources,
        "kb_id": kb_id,
        "question": question,
    }
