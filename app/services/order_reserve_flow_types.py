# app/services/order_reserve_flow_types.py
from __future__ import annotations

from typing import Optional


def extract_ext_order_no(platform: str, shop_id: str, ref: str) -> Optional[str]:
    plat = platform.upper()
    if ref.startswith(f"ORD:{plat}:{shop_id}:"):
        return ref.split(":", 3)[-1]
    return None
