# app/services/purchase_order_qty.py
from __future__ import annotations

from typing import Any

from app.services.qty_base import ordered_base as _ordered_base_impl
from app.services.qty_base import received_base as _received_base_impl


def get_qty_ordered_base(ln: Any) -> int:
    """
    ✅ Phase 2：最小单位订购事实（base）
    统一委托 app/services/qty_base.py
    """
    return int(_ordered_base_impl(ln) or 0)


def get_qty_received_base(ln: Any) -> int:
    """
    ✅ Phase 2：最小单位已收事实（base）
    统一委托 app/services/qty_base.py
    """
    return int(_received_base_impl(ln) or 0)


def safe_upc(v: Any) -> int:
    try:
        n = int(v or 1)
    except Exception:
        n = 1
    return n if n > 0 else 1


def base_to_purchase(base_qty: int, upc: int) -> int:
    """
    展示用：把 base 换算为采购单位（向下取整）。
    """
    if upc <= 0:
        return int(base_qty)
    return int(base_qty) // int(upc)
