"""
认证服务 — 用户注册/登录/查询
"""
from models.db_models import get_session, User, gen_id
from core.security import hash_password, verify_password, create_access_token


def create_user(username: str, password: str, role: str = "user",
                tags: str = "") -> dict:
    """注册新用户，返回用户数据字典（避免 ORM 对象脱离会话后无法访问）"""
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
        session.flush()  # 触发 INSERT，使 user.id 等属性可用
        # 在会话关闭前转为 dict，彻底避免 detached instance 问题
        user_dict = {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "tags": user.tags or "",
            "is_active": user.is_active,
        }
        session.commit()
        return user_dict
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def authenticate_user(username: str, password: str) -> dict | None:
    """验证用户登录，成功返回用户数据字典，失败返回 None"""
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username, is_active=1).first()
        if not user or not verify_password(password, user.password_hash):
            return None
        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "tags": user.tags or "",
            "is_active": user.is_active,
        }
    finally:
        session.close()


def get_user_by_id(user_id: str) -> User | None:
    """按 ID 查询用户（不限状态，供管理后台使用）"""
    session = get_session()
    try:
        return session.query(User).filter_by(id=user_id).first()
    finally:
        session.close()


def login_response(user: dict) -> dict:
    """生成登录响应（user 为字典，兼容 create_user 和 authenticate_user 的返回值）"""
    token = create_access_token(user["id"], user["username"], user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "tags": user.get("tags", ""),
            "is_active": user.get("is_active", 1),
        },
    }


# ═══════════════════════════════════════════════════════════
# 用户管理（admin 专属）
# ═══════════════════════════════════════════════════════════

def list_users() -> list[User]:
    """列出所有用户"""
    session = get_session()
    try:
        return session.query(User).order_by(User.created_at.desc()).all()
    finally:
        session.close()


def update_user(user_id: str, tags: str = None, role: str = None,
                is_active: int = None) -> dict | None:
    """更新用户信息，返回用户数据字典"""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return None
        if tags is not None:
            user.tags = tags
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        session.flush()
        user_dict = {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "tags": user.tags or "",
            "is_active": user.is_active,
        }
        session.commit()
        return user_dict
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_user(user_id: str) -> bool:
    """删除用户"""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False
        session.delete(user)
        session.commit()
        return True
    finally:
        session.close()
