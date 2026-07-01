"""
标签目录 API — 标签列表查询 + admin 管理
"""
from fastapi import APIRouter, HTTPException, Depends

from models.schemas import TagResponse, TagCreateRequest
from services import kb_service
from api.dependencies import require_admin

router = APIRouter(prefix="/api/v1", tags=["标签"])


# ── 公开访问（注册页需要，无需登录）──────────────────

@router.get("/tags", response_model=list[TagResponse])
def list_tags():
    """获取可选标签列表（公开，供注册和下拉选择使用）"""
    tags = kb_service.list_tags()
    return [TagResponse(**t) for t in tags]


# ── admin 专属 ────────────────────────────────────────

@router.post("/admin/tags", response_model=TagResponse)
def create_tag(req: TagCreateRequest, current_user=Depends(require_admin)):
    """新建标签（admin 专属）"""
    try:
        tag = kb_service.create_tag(req.name.strip())
        return TagResponse(**tag)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/admin/tags/{tag_id}")
def delete_tag(tag_id: str, current_user=Depends(require_admin)):
    """删除标签（admin 专属）"""
    ok = kb_service.delete_tag(tag_id)
    if not ok:
        raise HTTPException(status_code=404, detail="标签不存在")
    return {"message": "已删除"}
