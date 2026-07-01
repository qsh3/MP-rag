"""
管理员 API — 用户管理
"""
from fastapi import APIRouter, HTTPException, Depends

from models.schemas import UserInfo, AdminUpdateUserRequest
from api.dependencies import get_current_user, require_admin
from services import auth_service

router = APIRouter(prefix="/api/v1/admin", tags=["管理"])


@router.get("/users", response_model=list[UserInfo])
def list_users(current_user=Depends(require_admin)):
    users = auth_service.list_users()
    return [
        UserInfo(
            id=u.id, username=u.username, role=u.role,
            tags=u.tags or "", is_active=u.is_active,
        ) for u in users
    ]


@router.put("/users/{user_id}", response_model=UserInfo)
def update_user(user_id: str, req: AdminUpdateUserRequest,
                current_user=Depends(require_admin)):
    """更新用户（标签/角色/状态）— 不允许修改管理员"""
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.role == "admin":
        raise HTTPException(status_code=403, detail="不允许修改管理员账号的标签或角色")
    try:
        user = auth_service.update_user(
            user_id,
            tags=req.tags,
            role=req.role,
            is_active=req.is_active,
        )
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return UserInfo(
            id=user["id"], username=user["username"], role=user["role"],
            tags=user.get("tags", ""), is_active=user.get("is_active", 1),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.delete("/users/{user_id}")
def delete_user(user_id: str, current_user=Depends(require_admin)):
    """删除用户 — 不允许删除管理员"""
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.role == "admin":
        raise HTTPException(status_code=403, detail="不允许删除管理员账号")
    ok = auth_service.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=500, detail="删除失败")
    return {"message": "已删除"}
