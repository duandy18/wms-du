# app/shipping_assist/quote/pricing.py
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class PricingRowLike(Protocol):
    pricing_mode: object
    flat_amount: object
    base_amount: object
    rate_per_kg: object


def _calc_base_amount(
    row: PricingRowLike,
    billable_weight_kg: float,
    template_rounding: Optional[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """
    Base 定价（Level-3 终态）：
    - flat         : flat_amount（元/票）
    - linear_total : base_amount(面单费/基础费, 元/票) + rate_per_kg(元/kg) * billable_weight_kg
    - manual_quote : 人工报价

    重要合同：
    - billable_weight_kg 已由 _compute_billable_weight_kg 计算并完成 rounding（进位/取整）
    - 此处不得对 weight 再做第二次 rounding，避免 double-rounding
    - template_rounding 参数保留用于兼容调用链/调试信息，但不再参与计费重计算
    """
    w = float(billable_weight_kg)

    _ = template_rounding

    mode = (getattr(row, "pricing_mode", None) or "").strip().lower()

    if mode == "manual_quote":
        return 0.0, {
            "kind": "manual_quote",
            "message": "manual quote required",
            "billable_weight_kg": w,
            "source": "structured",
        }

    if mode == "flat":
        flat_amount = getattr(row, "flat_amount", None)
        amount = float(flat_amount or 0.0)
        return amount, {
            "kind": "flat",
            "amount": amount,
            "billable_weight_kg": w,
            "source": "structured",
        }

    if mode == "linear_total":
        base_amount = getattr(row, "base_amount", None)
        rate_per_kg = getattr(row, "rate_per_kg", None)
        base = float(base_amount or 0.0)
        rate = float(rate_per_kg or 0.0)
        amount = base + (rate * w)
        return amount, {
            "kind": "linear_total",
            "base_amount": base,
            "rate_per_kg": rate,
            "billable_weight_kg": w,
            "amount": amount,
            "source": "structured",
        }

    return 0.0, {
        "kind": "manual_quote",
        "message": f"unsupported pricing_mode={mode}",
        "billable_weight_kg": w,
        "source": "structured",
    }
