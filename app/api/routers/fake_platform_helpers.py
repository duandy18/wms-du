# app/api/routers/fake_platform_helpers.py
from __future__ import annotations

from typing import Optional


def build_order_ref(platform: str, shop_id: str, ext_order_no: str) -> str:
    plat = platform.upper()
    return f"ORD:{plat}:{shop_id}:{ext_order_no}"


def normalize_platform(platform: Optional[str]) -> Optional[str]:
    return platform.upper().strip() if platform else None
