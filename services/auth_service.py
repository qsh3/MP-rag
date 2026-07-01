"""
认证服务 — 用户注册/登录/查询
"""
from models.db_models import get_session, User, gen_id
from core.security import hash_password, verify_password, create_access_token


def create_user(username: str, password: str, role: str = "user",
                tags: str = "") -> User:
    """注册新用户"""
    session = get_session()
    try:
        existing = session.query(User).filter_by(username=username).first()
        if existing:
            raise ValueError(f"用户名 {username} 已存在")
        user = User(
            id=gen_id(),
            username=username,
            password_hash=hash_password(password),
            role=role,
            tags=tags,
            is_active=1,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def authenticate_user(username: str, password: str) -> User | None:
    """验证用户登录，成功返回 User，失败返回 None"""
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username, is_active=1).first()
        if not user or not verify_password(password, user.password_hash):
            return None
        return user
    finally:
        session.close()


def get_user_by_id(user_id: str) -> User | None:
    """按 ID 查询用户"""
    session = get_session()
    try:
        return session.query(User).filter_by(id=user_id, is_active=1).first()
    finally:
        session.close()


def login_response(user: User) -> dict:
    """生成登录响应"""
    token = create_access_token(user.id, user.username, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "tags": user.tags or "",
            "is_active": user.is_active,
        },
    }
