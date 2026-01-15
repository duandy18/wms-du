# app/services/receive_task_create/common.py
from __future__ import annotations

from typing import Optional, Any

from app.services.qty_base import ordered_base as _ordered_base
from app.services.qty_base import received_base as _received_base
from app.services.qty_base import safe_upc as _safe_upc


def safe_upc(v: Optional[int]) -> int:
    """
    units_per_case 的安全取值（compat）：
    - 真实实现见 app/services/qty_base.py
    """
    return _safe_upc(v)


def received_base(qty_received_base: Optional[int]) -> int:
    """
    ✅ 约定：PO 行 qty_received 为最小单位（base units）

    compat：
    - receive_task_create 侧历史上以 Optional[int] 传入 qty_received
    - 统一委托到 app/services/qty_base.py
    """
    class _Obj:
        qty_received = qty_received_base

    return _received_base(_Obj())


def ordered_base_from_line(obj: Any) -> int:
    """
    ✅ Phase 2：优先使用 qty_ordered_base（最小单位订购事实字段）

    compat：
    - 真实实现见 app/services/qty_base.py::ordered_base
    - services 运行时禁止散落乘法
    """
    return _ordered_base(obj)
