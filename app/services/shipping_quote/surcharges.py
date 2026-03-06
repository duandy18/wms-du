# app/services/shipping_quote/surcharges.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.models.shipping_provider_surcharge import ShippingProviderSurcharge

from .types import Dest, _s


JsonObject = Dict[str, object]


def _dest_code(v: object | None) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _cond_match(s: ShippingProviderSurcharge, dest: Dest, flags: List[str]) -> bool:
    """
    结构化 surcharge 条件匹配：
    - always
    - province
    - city
    """
    _ = flags

    scope = str(getattr(s, "scope", "") or "").strip().lower()

    if scope == "always":
        return True

    prov_code = _dest_code(getattr(dest, "province_code", None))
    city_code = _dest_code(getattr(dest, "city_code", None))

    row_prov_code = _dest_code(getattr(s, "province_code", None))
    row_city_code = _dest_code(getattr(s, "city_code", None))
    row_prov_name = _s(getattr(s, "province_name", None))
    row_city_name = _s(getattr(s, "city_name", None))

    if scope == "province":
        if row_prov_code and prov_code:
            return row_prov_code == prov_code
        return row_prov_name != "" and row_prov_name == _s(dest.province)

    if scope == "city":
        province_ok = False
        if row_prov_code and prov_code:
            province_ok = row_prov_code == prov_code
        elif row_prov_name:
            province_ok = row_prov_name == _s(dest.province)

        if not province_ok:
            return False

        if row_city_code and city_code:
            return row_city_code == city_code
        return row_city_name != "" and row_city_name == _s(dest.city)

    return False


def _calc_surcharge_amount(
    s: ShippingProviderSurcharge,
    billable_weight_kg: float,
    scheme_rounding: Optional[JsonObject],
) -> Tuple[float, JsonObject]:
    """
    surcharge 终态金额计算：

    - 只支持 fixed_amount
    - 重量 / 体积重 / rounding / 倍率，全部属于基础运费链
    - surcharge 只表达“每单加多少钱”
    """
    _ = billable_weight_kg
    _ = scheme_rounding

    amt = float(getattr(s, "fixed_amount", 0) or 0.0)
    return amt, {"kind": "fixed", "amount": amt}
