# app/api/routers/shipping_provider_pricing_schemes/validators.py
from __future__ import annotations

_ALLOWED_DEFAULT_PRICING_MODES = {"flat", "linear_total", "step_over"}


def validate_default_pricing_mode(v: str) -> str:
    """
    方案默认口径（scheme 级）只允许：
    - flat
    - linear_total
    - step_over

    注意：
    - manual_quote 可以出现在 matrix cell 上作为兜底方式
    - 但不允许作为 scheme 默认口径
    """
    t = (v or "").strip().lower()
    if t not in _ALLOWED_DEFAULT_PRICING_MODES:
        raise ValueError("default_pricing_mode must be one of: flat / linear_total / step_over")
    return t
