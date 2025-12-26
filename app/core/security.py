# app/core/security.py
"""
安全工具（统一入口）：

- 正式路径：PyJWT + passlib[pbkdf2_sha256]
- 强制规则（2025-12）：
    * 非 dev 环境必须显式配置 JWT_SECRET
    * 禁止使用 dev 默认 secret 启动服务
    * 任何环境禁止 alg=none
- dev / CI 环境允许最小实现兜底（但仍必须是 HS256）
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
_JWT_ALG = "HS256"

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
# HS256 (no external deps) minimal JWT helpers (dev/CI fallback)
# - 禁止 alg=none
# - 仅用于 PyJWT 不可用时
# ---------------------------
def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def _hs256_sign(message: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    return _b64url_encode(sig)


def _create_jwt_hs256(payload: Dict[str, Any], secret: str) -> str:
    header = {"alg": _JWT_ALG, "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig_b64 = _hs256_sign(signing_input, secret)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def _decode_jwt_hs256(token: str, secret: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        if not isinstance(header, dict):
            return None

        # 禁止 alg=none，且仅接受 HS256
        if header.get("alg") != _JWT_ALG:
            return None

        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = _hs256_sign(signing_input, secret)
        if not hmac.compare_digest(expected_sig, sig_b64):
            return None

        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if not isinstance(payload, dict):
            return None

        # exp 校验（与 PyJWT 行为一致：过期返回 None）
        exp = payload.get("exp")
        if exp is not None:
            try:
                exp_int = int(exp)
            except Exception:
                return None
            if int(time.time()) >= exp_int:
                return None

        return payload
    except Exception:
        return None


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
            out = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALG])  # type: ignore
            return out if isinstance(out, dict) else None
        except Exception:
            return None

# ---------------------------
# 兜底：开发期最小实现（仅 dev / CI）
# - 注意：即使兜底，也必须生成/校验 HS256（禁止 alg=none）
# ---------------------------
except Exception:
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
        payload = dict(data)
        payload["exp"] = int(time.time()) + 60 * (expires_minutes or _JWT_EXP_MIN)
        return _create_jwt_hs256(payload, _JWT_SECRET)

    def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
        return _decode_jwt_hs256(token, _JWT_SECRET)


# ---------------------------
# 兼容别名（保持旧代码能用）
# ---------------------------
hash_password = get_password_hash
