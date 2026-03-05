# app/services/purchase_order_qty.py
from __future__ import annotations

from typing import Any


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


def get_qty_ordered_base(ln: Any) -> int:
    """
    ✅ Phase 2：最小单位订购事实（base）
    主线：优先 qty_ordered_base（DB 已收敛并加 CHECK）。
    """
    try:
        return max(int(getattr(ln, "qty_ordered_base", 0) or 0), 0)
    except Exception:
        return 0
