# app/services/qty_base.py
from __future__ import annotations

from typing import Any, Optional


def safe_upc(v: Optional[int]) -> int:
    """
    units_per_case 的安全取值：
    - None / 非法 / <=0 => 1（避免除零/负数导致的灾难）
    """
    try:
        n = int(v or 0)
    except Exception:
        n = 0
    return n if n > 0 else 1


def ordered_base(obj: Any) -> int:
    """
    ✅ Phase 2：最小单位订购事实（base units）

    优先使用 qty_ordered_base（最小单位订购事实字段）。

    ⚠️ Legacy fallback（唯一允许的乘法位置）：
    - 仅当旧数据缺失 qty_ordered_base 时，才允许用 qty_ordered * units_per_case 推导 base。
    - services 运行时其余位置禁止散落乘法与跨口径比较。
    """
    qob = getattr(obj, "qty_ordered_base", None)
    if qob is not None:
        try:
            return max(int(qob or 0), 0)
        except Exception:
            return 0

    upc = safe_upc(getattr(obj, "units_per_case", None))
    try:
        ordered_purchase = int(getattr(obj, "qty_ordered") or 0)
    except Exception:
        ordered_purchase = 0

    return max(ordered_purchase * upc, 0)


def received_base(obj: Any) -> int:
    """
    ✅ Phase 2：最小单位已收事实（base units）

    约定：qty_received 为最小单位（base）。
    """
    try:
        return max(int(getattr(obj, "qty_received", 0) or 0), 0)
    except Exception:
        return 0


def remaining_base(obj: Any) -> int:
    """
    ✅ remaining_base（base）= ordered_base - received_base
    """
    return max(ordered_base(obj) - received_base(obj), 0)
