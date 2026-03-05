# app/services/shipping_quote/pricing.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket


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

    ✅ 重要合同（本轮落地）：
    - billable_weight_kg 已由 _compute_billable_weight_kg 计算并完成 rounding（进位/取整）。
    - 此处不得对 weight 再做第二次 rounding，避免 double-rounding 造成误差与不可解释。
    - scheme_rounding 参数保留以兼容旧调用链/调试信息，但不再参与计费重计算。
    """
    # ✅ 最终计费重：不再二次取整
    w = float(billable_weight_kg)

    # scheme_rounding 已不再用于计算，但保留参数避免牵连
    _ = scheme_rounding

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
