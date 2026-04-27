# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/pdd/sign.py
from __future__ import annotations

import hashlib
from typing import Mapping


def build_pdd_sign(
    *,
    params: Mapping[str, object],
    client_secret: str,
) -> str:
    """
    拼多多开放平台签名：

    1. 所有参数按 key 的 ASCII 升序排序
    2. 按 key + value 无缝拼接
    3. 头尾分别拼接 client_secret
    4. MD5 后转大写
    """
    secret = str(client_secret or "").strip()
    if not secret:
        raise ValueError("client_secret is required for pdd sign")

    items: list[tuple[str, str]] = []
    for key, value in params.items():
        k = str(key or "").strip()
        if not k:
            continue
        if value is None:
            continue
        v = str(value)
        items.append((k, v))

    items.sort(key=lambda item: item[0])

    content = "".join(f"{k}{v}" for k, v in items)
    raw = f"{secret}{content}{secret}".encode("utf-8")
    return hashlib.md5(raw).hexdigest().upper()
