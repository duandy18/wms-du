# app/core/security.py
"""
安全工具（统一入口）：

- 正式路径：PyJWT + passlib[pbkdf2_sha256]
- 强制规则（2025-12）：
    * 非 dev 环境必须显式配置 JWT_SECRET
    * 禁止使用 dev 默认 secret 启动服务
- dev / CI 环境允许最小实现兜底
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
            ENV: str = os.environ.get("ENV", "dev")
            JWT_SECRET: str = os.environ.get("JWT_SECRET", "dev-temp-secret")
            ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
                os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
            )

        settings = _Settings()  # type: ignore[assignment]

# ---------------------------
# 强制安全检查（启动即执行）
# ---------------------------
_ENV = getattr(settings, "ENV", "dev")
_JWT_SECRET = getattr(settings, "JWT_SECRET", "")
_JWT_EXP_MIN = int(getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60))

_DEV_SECRETS = {
    "",
    "dev-temp-secret",
    "dev-secret-change-me",
}

if _ENV != "dev":
    if not _JWT_SECRET or _JWT_SECRET in _DEV_SECRETS:
        raise RuntimeError(
            "❌ SECURITY ERROR: JWT_SECRET is not properly configured.\n\n"
            f"ENV = {_ENV!r}\n"
            "You are running in a non-dev environment, but JWT_SECRET is missing "
            "or still using a development default value.\n\n"
            "Fix:\n"
            "  - Set a strong JWT_SECRET via environment variable or .env file\n"
            "  - Restart the application\n"
        )

# ---------------------------
# 正式依赖路径：PyJWT + passlib[pbkdf2_sha256]
# ---------------------------
try:
    import jwt  # PyJWT
    from passlib.context import CryptContext

    _pwd_context = CryptContext(
        schemes=["pbkdf2_sha256"],
        deprecated="auto",
    )
    _JWT_ALG = "HS256"

    def get_password_hash(password: str) -> str:
        return _pwd_context.hash(password)

    def verify_password(plain_password: str, password_hash: str) -> bool:
        try:
            return _pwd_context.verify(plain_password, password_hash)
        except Exception:
            return False

    def create_access_token(
        data: Dict[str, Any],
        expires_minutes: Optional[int] = None,
    ) -> str:
        payload = dict(data)
        payload["exp"] = int(time.time()) + 60 * (expires_minutes or _JWT_EXP_MIN)
        return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALG)

    def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
        try:
            return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALG])  # type: ignore
        except Exception:
            return None

# ---------------------------
# 兜底：开发期最小实现（仅 dev / CI）
# ---------------------------
except Exception:
    #
    # ⚠️ 只允许在 dev 环境使用
    #
    if _ENV != "dev":
        raise RuntimeError(
            "❌ SECURITY ERROR: PyJWT / passlib not available in non-dev environment.\n"
            "Install required dependencies instead of relying on fallback."
        )

    def get_password_hash(password: str) -> str:
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

    def create_access_token(
        data: Dict[str, Any],
        expires_minutes: Optional[int] = None,
    ) -> str:
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
