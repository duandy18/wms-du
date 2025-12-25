# app/services/shipping_quote/weight.py
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


def _round_weight(weight: float, rounding: Optional[Dict[str, Any]]) -> float:
    """
    rounding = {"mode":"ceil","step_kg":1.0}
    """
    if weight < 0:
        return weight
    if not rounding:
        return weight

    mode = str(rounding.get("mode") or "ceil").lower()
    step = float(rounding.get("step_kg") or 1.0)
    if step <= 0:
        step = 1.0

    q = weight / step

    if mode == "ceil":
        return math.ceil(q) * step
    if mode == "floor":
        return math.floor(q) * step
    if mode == "round":
        return round(q) * step
    return math.ceil(q) * step


def _compute_billable_weight_kg(
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    rule: Optional[Dict[str, Any]],
) -> Dict[str, float]:
    """
    billable_weight_rule 示例：
      {"divisor_cm":8000,"rounding":{"mode":"ceil","step_kg":1.0}}
    """
    real = float(real_weight_kg or 0.0)
    vol = 0.0

    divisor = None
    rounding = None
    if rule:
        divisor = rule.get("divisor_cm") or rule.get("divisor") or None
        rounding = rule.get("rounding")

    if dims_cm and divisor:
        try:
            d = float(divisor)
            if d > 0:
                length_cm, width_cm, height_cm = dims_cm
                vol = (float(length_cm) * float(width_cm) * float(height_cm)) / d
        except Exception:
            vol = 0.0

    billable_raw = max(real, vol)
    billable = _round_weight(billable_raw, rounding)

    return {
        "real_weight_kg": real,
        "vol_weight_kg": vol,
        "billable_weight_kg_raw": billable_raw,
        "billable_weight_kg": billable,
    }
