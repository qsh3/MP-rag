"""
安全工具 — 密码哈希 + JWT 签发/验证
"""
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS


def hash_password(plain: str) -> str:
    """bcrypt 哈希密码"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, username: str, role: str) -> str:
    """签发 JWT access token"""
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """解码 JWT token，失败返回 None"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
