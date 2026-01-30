# app/services/shipping_quote/surcharges.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .types import Dest, _s


def _cond_match(condition: Dict[str, Any], dest: Dest, flags: List[str]) -> bool:
    cond = condition or {}
    flags_norm = set([f.strip().lower() for f in (flags or []) if f and f.strip()])

    flag_any = cond.get("flag_any")
    if isinstance(flag_any, list) and flag_any:
        want = set([str(x).strip().lower() for x in flag_any if x])
        if want and flags_norm.isdisjoint(want):
            return False

    d = cond.get("dest")
    if isinstance(d, dict):
        provs = d.get("province")
        cities = d.get("city")
        dists = d.get("district")
        if isinstance(provs, list) and provs:
            if _s(dest.province) not in [str(x).strip() for x in provs]:
                return False
        if isinstance(cities, list) and cities:
            if _s(dest.city) not in [str(x).strip() for x in cities]:
                return False
        if isinstance(dists, list) and dists:
            if _s(dest.district) not in [str(x).strip() for x in dists]:
                return False

    return True


def _calc_surcharge_amount(
    amount_json: Dict[str, Any],
    billable_weight_kg: float,
    scheme_rounding: Optional[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """
    ✅ 重要合同（本轮落地）：
    - billable_weight_kg 已由 _compute_billable_weight_kg 计算并完成 rounding（进位/取整）。
    - 附加费计算不得对 weight 再做第二次 rounding，避免 double-rounding。
    - amount_json.rounding / scheme_rounding 参数保留以兼容旧配置与未来解释，但不再参与计费重计算。
    """
    aj = amount_json or {}
    kind = str(aj.get("kind") or "flat").lower()

    # ✅ 最终计费重：不再二次取整
    w = float(billable_weight_kg)

    # rounding 已不再用于计算，但保留变量（便于未来解释/审计，不影响本轮合同）
    _ = aj.get("rounding") or scheme_rounding

    if kind == "flat":
        amt = float(aj.get("amount") or 0.0)
        return amt, {"kind": "flat", "amount": amt}

    if kind == "per_kg":
        rate = float(aj.get("rate_per_kg") or 0.0)
        amt = rate * w
        return amt, {"kind": "per_kg", "rate_per_kg": rate, "billable_weight_kg": w, "amount": amt}

    if kind == "table":
        rules = aj.get("rules") or []
        default_amt = float(aj.get("default_amount") or 0.0)

        picked = None
        for r in rules:
            try:
                mx = r.get("max_kg")
                if mx is None:
                    continue
                if w <= float(mx) + 1e-9:
                    picked = r
                    break
            except Exception:
                continue

        if picked is not None:
            amt = float(picked.get("amount") or 0.0)
            return amt, {"kind": "table", "picked": picked, "billable_weight_kg": w, "amount": amt}

        return default_amt, {
            "kind": "table",
            "picked": None,
            "billable_weight_kg": w,
            "amount": default_amt,
        }

    amt = float(aj.get("amount") or 0.0)
    return amt, {"kind": "flat", "amount": amt}
