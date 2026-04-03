# app/wms/procurement/services/qty_base.py
from __future__ import annotations

from typing import Any


def ordered_base(obj: Any) -> int:
    """
    M-4 之后：
    订购事实唯一来源：qty_ordered_base
    """
    try:
        return max(int(getattr(obj, "qty_ordered_base", 0) or 0), 0)
    except Exception:
        return 0


def received_base(obj: Any) -> int:
    """
    M-4 之后：
    收货事实唯一来源：qty_base
    """
    try:
        return max(int(getattr(obj, "qty_base", 0) or 0), 0)
    except Exception:
        return 0


def remaining_base(obj: Any) -> int:
    return max(ordered_base(obj) - received_base(obj), 0)
