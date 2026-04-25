# app/shipping_assist/shipment/waybill_top_sign.py
from __future__ import annotations

import hashlib
from typing import Any, Mapping


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_top_sign(params: Mapping[str, Any], app_secret: str) -> str:
    items: list[tuple[str, str]] = []
    for key, value in params.items():
        if key == "sign":
            continue
        if value is None:
            continue
        items.append((str(key), _stringify(value)))

    items.sort(key=lambda item: item[0])

    message = app_secret
    for key, value in items:
        message += key
        message += value
    message += app_secret

    md5 = hashlib.md5()
    md5.update(message.encode("utf-8"))
    return md5.hexdigest().upper()
