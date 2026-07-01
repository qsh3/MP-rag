"""
认证 API — 注册 / 登录 / 当前用户
"""
import traceback
from fastapi import APIRouter, HTTPException, Depends

from models.schemas import RegisterRequest, LoginRequest, TokenResponse, UserInfo
from api.dependencies import get_current_user
from services.auth_service import create_user, authenticate_user, login_response
from models.db_models import User

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    """注册新用户（公开）"""
    try:
        user = create_user(req.username, req.password, role="user", tags=req.tags)
        return login_response(user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"注册失败: {e}")


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """用户登录"""
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return login_response(user)


@router.get("/me", response_model=UserInfo)
def me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserInfo(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        tags=current_user.tags or "",
        is_active=current_user.is_active,
    )
