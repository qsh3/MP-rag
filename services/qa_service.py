"""
问答服务 — RAGFlow 检索 + DeepSeek 生成
"""
import json

from rag_client import get_client as get_rag_client
from services.llm_service import generate_rag_stream, generate, RAG_SYSTEM_PROMPT
from services.kb_service import save_chat, save_evaluation_record


def _extract_keywords(question: str) -> str:
    """用 LLM 从问题中提取检索关键词（短查询优化）"""
    if len(question) <= 3:
        # 问题太短，直接返回原问题作为关键词
        return question
    try:
        prompt = f"""从以下问题中提取 3-5 个最关键的检索关键词，用空格分隔。
只输出关键词，不要解释。

问题：{question}
关键词："""
        keywords = generate(
            [{"role": "user", "content": prompt}],
            temperature=0,
            stream=False,
        )
        if isinstance(keywords, str) and keywords.strip():
            return keywords.strip()
    except Exception:
        pass
    return ""


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

    # 2. 提取关键词增强检索
    keywords = _extract_keywords(question)
    search_query = f"{question} | {keywords}" if keywords else question

    if not dataset_id and not rag.available:
        search_results = rag._local_search(search_query, top_k)
    else:
        # 3. RAGFlow 混合检索（关键词增强）
        search_results = rag.search(dataset_id, search_query, top_k)
        # 首次无结果则用原始问题重试
        if not search_results and keywords:
            search_results = rag.search(dataset_id, question, top_k)

    # 4. 构建上下文
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

    # 关键词增强检索
    keywords = _extract_keywords(question)
    search_query = f"{question} | {keywords}" if keywords else question

    if dataset_id or rag.available:
        search_results = rag.search(dataset_id, search_query, top_k)
        if not search_results and keywords:
            search_results = rag.search(dataset_id, question, top_k)
    else:
        search_results = rag._local_search(search_query, top_k)

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
