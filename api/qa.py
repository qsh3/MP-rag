"""
问答 API — SSE 流式 + 非流式
"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.schemas import AskRequest, AskResponse, SourceDoc
from services import kb_service, qa_service

router = APIRouter(prefix="/api/v1/qa", tags=["问答"])


@router.post("/ask")
async def ask_question(req: AskRequest):
    """提问 — 支持流式(SSE)和非流式

    stream=true (默认): 返回 SSE 事件流
      - event: sources  → 来源文档列表
      - event: token    → 逐字生成内容
      - event: done     → 完成信号
      - event: error    → 错误信息

    stream=false: 返回完整 JSON
    """
    # 验证知识库存在
    kb = kb_service.get_kb(req.kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    if req.stream:
        def sse_generator():
            try:
                for chunk in qa_service.ask_stream(
                    req.kb_id, req.question, req.top_k, req.session_id
                ):
                    event = chunk.get("event", "message")
                    data = chunk.get("data", "")
                    if not isinstance(data, str):
                        data = json.dumps(data, ensure_ascii=False)
                    yield f"event: {event}\ndata: {data}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {str(e)}\n\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        result = qa_service.ask_sync(req.kb_id, req.question, req.top_k)
        sources = [SourceDoc(**s) for s in result.get("sources", [])]
        return AskResponse(
            answer=result["answer"],
            sources=sources,
            kb_id=req.kb_id,
            question=req.question,
        )


@router.get("/history/{kb_id}")
def get_history(kb_id: str):
    """获取知识库的问答历史"""
    kb = kb_service.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    history = kb_service.get_chat_history(kb_id)
    return {"total": len(history), "items": history}


@router.delete("/session/{kb_id}/{session_id}")
def delete_session(kb_id: str, session_id: str):
    """删除整个会话的所有聊天记录"""
    count = kb_service.delete_session_history(kb_id, session_id)
    return {"message": f"已删除 {count} 条记录"} if count else {"message": "无记录"}


@router.delete("/history/{chat_id}")
def delete_history(chat_id: str):
    """删除单条聊天记录"""
    from models.db_models import get_session, ChatHistory
    session = get_session()
    try:
        chat = session.query(ChatHistory).filter_by(id=chat_id).first()
        if chat:
            session.delete(chat)
            session.commit()
            return {"message": "已删除"}
        raise HTTPException(status_code=404, detail="记录不存在")
    finally:
        session.close()
