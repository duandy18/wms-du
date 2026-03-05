# app/services/shipping_quote/calc.py
from __future__ import annotations

# ✅ 兼容层（历史 import 不改，内部实现已拆分）
# - calc_quote：主算价入口
# - _scheme_is_effective / _check_scheme_warehouse_allowed：历史内部引用点
#
# 注意：新实现分别位于：
# - calc_quote.py
# - calc_core.py

from .calc_core import check_scheme_warehouse_allowed as _check_scheme_warehouse_allowed
from .calc_core import scheme_is_effective as _scheme_is_effective
from .calc_quote import calc_quote

__all__ = [
    "calc_quote",
    "_scheme_is_effective",
    "_check_scheme_warehouse_allowed",
]
