# app/services/shipping_quote/pricing.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket

from .weight import _round_weight


def _calc_base_amount(
    bracket: ShippingProviderZoneBracket,
    billable_weight_kg: float,
    scheme_rounding: Optional[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """
    Base 定价（不兼容收敛版）：
    - flat         : flat_amount（元/票）
    - linear_total : base_amount(面单费/基础费, 元/票) + rate_per_kg(元/kg) * billable_weight_kg
    - manual_quote : 人工报价
    """
    # rounding：Bracket 不再覆盖 Scheme（你说删字段了，这里只走 scheme_rounding）
    w = _round_weight(float(billable_weight_kg), scheme_rounding)

    mode = (getattr(bracket, "pricing_mode", None) or "").strip().lower()

    if mode == "manual_quote":
        return 0.0, {
            "kind": "manual_quote",
            "message": "manual quote required",
            "billable_weight_kg": w,
            "source": "structured",
        }

    if mode == "flat":
        fa = getattr(bracket, "flat_amount", None)
        amt = float(fa or 0.0)
        return amt, {
            "kind": "flat",
            "amount": amt,
            "billable_weight_kg": w,
            "source": "structured",
        }

    if mode == "linear_total":
        base_amt = getattr(bracket, "base_amount", None)
        rate = getattr(bracket, "rate_per_kg", None)
        b = float(base_amt or 0.0)
        r = float(rate or 0.0)
        amt = b + (r * w)
        return amt, {
            "kind": "linear_total",
            "base_amount": b,
            "rate_per_kg": r,
            "billable_weight_kg": w,
            "amount": amt,
            "source": "structured",
        }

    return 0.0, {
        "kind": "manual_quote",
        "message": f"unsupported pricing_mode={mode}",
        "billable_weight_kg": w,
        "source": "structured",
    }
