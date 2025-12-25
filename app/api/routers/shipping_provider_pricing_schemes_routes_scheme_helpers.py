# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_helpers.py
from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def seg_item_to_dict(x: Any) -> dict:
    """
    兼容两种形态：
    - Pydantic model（有 model_dump）
    - 已经是 dict（来自 payload.model_dump / payload.dict 的路径）
    """
    if hasattr(x, "model_dump"):
        return x.model_dump()  # pydantic v2
    if isinstance(x, dict):
        return x
    raise HTTPException(status_code=422, detail="segments_json items must be objects")
