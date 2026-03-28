# app/oms/platforms/taobao/top_sign.py
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Mapping


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_top_sign(
    params: Mapping[str, Any],
    app_secret: str,
    *,
    sign_method: str = "md5",
) -> str:
    """
    构建 TOP sign。

    规则：
    - 排除 sign 本身和空键
    - 其余参数按 key 升序拼接 key + value
    - md5: secret + content + secret
    - hmac: HMAC(secret, content)

    注意：
    - 这里只做 TOP 协议 sign，不承载业务语义
    """
    sign_method = sign_method.lower().strip()
    items = []
    for key, value in params.items():
        if not key or key == "sign":
            continue
        if value is None:
            continue
        items.append((str(key), _normalize_value(value)))
    items.sort(key=lambda item: item[0])

    content = "".join(f"{key}{value}" for key, value in items)

    if sign_method == "md5":
        message = f"{app_secret}{content}{app_secret}".encode("utf-8")
        return hashlib.md5(message).hexdigest().upper()

    if sign_method == "hmac":
        digest = hmac.new(
            app_secret.encode("utf-8"),
            content.encode("utf-8"),
            hashlib.md5,
        ).hexdigest()
        return digest.upper()

    raise ValueError(f"unsupported sign_method: {sign_method!r}")
