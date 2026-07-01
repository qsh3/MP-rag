"""
知识库管理 API
"""
from fastapi import APIRouter, HTTPException, Depends
from models.schemas import (
    CreateKBRequest, UpdateKBRequest, KBResponse, KBListResponse,
)
from services import kb_service
from api.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/kb", tags=["知识库"])


@router.post("", response_model=KBResponse)
def create_kb(req: CreateKBRequest, current_user=Depends(get_current_user)):
    """创建知识库"""
    try:
        kb = kb_service.create_kb(req.name, req.description)
        return KBResponse(**kb)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=KBListResponse)
def list_kbs(current_user=Depends(get_current_user)):
    """列出所有知识库"""
    items = kb_service.list_kbs()
    return KBListResponse(total=len(items), items=[KBResponse(**i) for i in items])


@router.get("/{kb_id}", response_model=KBResponse)
def get_kb(kb_id: str, current_user=Depends(get_current_user)):
    """获取知识库详情"""
    kb = kb_service.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return KBResponse(**kb)


@router.put("/{kb_id}", response_model=KBResponse)
def update_kb(kb_id: str, req: UpdateKBRequest, current_user=Depends(get_current_user)):
    """更新知识库"""
    kb = kb_service.update_kb(kb_id, req.name, req.description)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return KBResponse(**kb)


@router.delete("/{kb_id}")
def delete_kb(kb_id: str, current_user=Depends(get_current_user)):
    """删除知识库及其所有文档"""
    ok = kb_service.delete_kb(kb_id)
    if not ok:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"message": "已删除"}
