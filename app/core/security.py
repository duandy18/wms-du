from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings  # 从 config.py 导入配置

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
)


def hash_password(plain: str) -> str:
    """
    对明文密码进行哈希
    """
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    验证明文密码和哈希值是否匹配
    """
    return pwd_context.verify(plain, hashed)


def create_access_token(sub: str, extra: dict[str, Any] | None = None) -> str:
    """
    创建一个 JWT 访问令牌
    """
    now = datetime.now(tz=UTC)
    exp = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": sub, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_token(token: str) -> dict[str, Any]:
    """
    解码一个 JWT 令牌
    """
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
