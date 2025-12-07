# app/core/security.py
"""
安全工具：
- 正式路径：PyJWT + passlib[pbkdf2_sha256]
- 从 app.core.config 加载配置：优先 `settings`，否则 `get_settings()`
- 若缺依赖或配置，则回退到开发期最小实现（仅本地/CI，不要用于生产）
- 对外提供统一接口：
    - get_password_hash / verify_password
    - create_access_token / decode_access_token
    - hash_password (get_password_hash 的别名，兼容旧代码)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any, Dict, Optional

# ---------------------------
# 配置加载：优先 settings，其次 get_settings()
# ---------------------------
try:
    from app.core.config import settings  # type: ignore[attr-defined]
except Exception:
    try:
        from app.core.config import get_settings  # type: ignore[attr-defined]

        settings = get_settings()  # type: ignore[assignment]
    except Exception:

        class _Settings:
            JWT_SECRET: str = os.environ.get("JWT_SECRET", "dev-secret-change-me")
            ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
                os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
            )

        settings = _Settings()  # type: ignore[assignment]

_JWT_SECRET = getattr(settings, "JWT_SECRET", "dev-secret-change-me")
_JWT_EXP_MIN = int(getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60))

# ---------------------------
# 正式依赖路径：PyJWT + passlib[pbkdf2_sha256]
# ---------------------------
try:
    import jwt  # PyJWT
    from passlib.context import CryptContext

    # 使用 pbkdf2_sha256，避免 bcrypt 72 字节限制
    _pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    _JWT_ALG = "HS256"

    def get_password_hash(password: str) -> str:
        """
        生成密码哈希（pbkdf2_sha256）。
        """
        return _pwd_context.hash(password)

    def verify_password(plain_password: str, password_hash: str) -> bool:
        """
        校验明文密码是否匹配给定哈希。
        """
        try:
            return _pwd_context.verify(plain_password, password_hash)
        except Exception:
            return False

    def create_access_token(data: Dict[str, Any], expires_minutes: Optional[int] = None) -> str:
        """
        创建 JWT 访问令牌。
        """
        payload = dict(data)
        payload["exp"] = int(time.time()) + 60 * (expires_minutes or _JWT_EXP_MIN)
        return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALG)

    def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
        """
        解码并验证 JWT 访问令牌。
        """
        try:
            return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALG])  # type: ignore[no-any-return]
        except Exception:
            return None


# ---------------------------
# 兜底：开发期最小实现（无外部依赖）
# ---------------------------
except Exception:
    #
    # 注意：仅在 PyJWT 或 passlib 无法导入时使用。
    # 生产环境请确保安装正式依赖。
    #

    def get_password_hash(password: str) -> str:
        """sha256 + 随机盐，格式：sha256$salt$hexdigest（仅开发/CI）"""
        salt = base64.urlsafe_b64encode(os.urandom(12)).decode("utf-8").rstrip("=")
        digest = hashlib.sha256((salt + ":" + password).encode("utf-8")).hexdigest()
        return f"sha256${salt}${digest}"

    def verify_password(plain_password: str, password_hash: str) -> bool:
        try:
            algo, salt, digest = password_hash.split("$", 2)
            if algo != "sha256":
                return False
            expected = hashlib.sha256((salt + ":" + plain_password).encode("utf-8")).hexdigest()
            return hmac.compare_digest(expected, digest)
        except Exception:
            return False

    def create_access_token(data: Dict[str, Any], expires_minutes: Optional[int] = None) -> str:
        """
        超轻 token：base64(header).base64(payload).exp_ts
        仅开发/CI使用；无签名校验。
        """
        exp = int(time.time()) + 60 * (expires_minutes or _JWT_EXP_MIN)
        header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode("utf-8").rstrip("=")
        payload_bytes = str({**data, "exp": exp}).encode("utf-8")
        payload = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        return f"{header}.{payload}.{exp}"

    def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
        try:
            parts = token.split(".")
            if len(parts) < 3:
                return None
            payload = base64.urlsafe_b64decode(parts[1] + "==")
            s = payload.decode("utf-8").strip()
            if s.startswith("{") and s.endswith("}"):
                s = s[1:-1]
            out: Dict[str, Any] = {}
            for part in s.split(","):
                if ":" in part:
                    k, v = part.split(":", 1)
                    out[k.strip().strip("'\"")] = v.strip().strip("'\"")
            return out
        except Exception:
            return None


# ---------------------------
# 兼容别名（保持旧代码能用）
# ---------------------------
hash_password = get_password_hash
