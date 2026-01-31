# app/services/shipping_quote/dest_adjustments.py
from __future__ import annotations

from typing import Dict, List

from app.models.pricing_scheme_dest_adjustment import PricingSchemeDestAdjustment
from .types import Dest

JsonObject = Dict[str, object]


def read_dest_keys(dest: Dest) -> tuple[str, str]:
    """
    ✅ 优先使用 code（province_code/city_code），没有则 fallback 到 name（province/city）。
    兼容期策略：不强依赖 Dest 已升级。
    """
    prov_code = getattr(dest, "province_code", None)
    city_code = getattr(dest, "city_code", None)

    prov_name = (dest.province or "").strip()
    city_name = (dest.city or "").strip()

    prov_key = (str(prov_code).strip() if prov_code is not None else "") or prov_name
    city_key = (str(city_code).strip() if city_code is not None else "") or city_name
    return prov_key, city_key


def match_dest_adjustments(
    rows: List[PricingSchemeDestAdjustment],
    dest: Dest,
    reasons: List[str],
) -> List[PricingSchemeDestAdjustment]:
    """
    ✅ 目的地附加费命中（结构化事实）：
    - 优先按 code 匹配（province_code/city_code）
    - 兼容期：若 dest 未提供 code，则用 province/city name 兜底
    - city wins：若 city 命中，则 province 被 suppressed（记录 reasons）
    """
    prov_key, city_key = read_dest_keys(dest)
    if not prov_key:
        return []

    hit_province: List[PricingSchemeDestAdjustment] = []
    hit_city: List[PricingSchemeDestAdjustment] = []

    for r in rows:
        if not bool(r.active):
            continue

        r_prov_key = (str(r.province_code).strip() if r.province_code else "") or (str(r.province).strip() if r.province else "")
        if r_prov_key != prov_key:
            continue

        sc = (r.scope or "").strip().lower()
        if sc == "province":
            hit_province.append(r)
        elif sc == "city":
            r_city_key = (str(r.city_code).strip() if r.city_code else "") or (str(r.city).strip() if r.city else "")
            if city_key and r_city_key == city_key:
                hit_city.append(r)

    chosen: List[PricingSchemeDestAdjustment] = []
    if hit_city:
        chosen.extend(sorted(hit_city, key=lambda x: int(x.id)))
        if hit_province:
            reasons.append(f"dest_adjustment_suppressed: province={prov_key} (city wins)")
    else:
        chosen.extend(sorted(hit_province, key=lambda x: int(x.id)))

    return chosen


def build_dest_adjustment_details(rows: List[PricingSchemeDestAdjustment], reasons: List[str]) -> tuple[List[JsonObject], float]:
    """
    将命中行转为 breakdown 明细，并写入 reasons。
    返回：(da_details, da_sum)
    """
    da_details: List[JsonObject] = []
    da_sum = 0.0

    for r in rows:
        amt = float(r.amount)
        da_sum += amt
        da_details.append(
            {
                "id": r.id,
                "scheme_id": r.scheme_id,
                "scope": r.scope,
                "province_code": r.province_code,
                "city_code": r.city_code,
                "province_name": r.province_name,
                "city_name": r.city_name,
                "province": r.province,
                "city": r.city,
                "amount": float(amt),
                "priority": int(getattr(r, "priority", 100) or 100),
            }
        )

        label_prov = (r.province_name or r.province_code or r.province or "").strip()
        label_city = (r.city_name or r.city_code or r.city or "").strip()
        if (r.scope or "").strip().lower() == "city":
            reasons.append(f"dest_adjustment_hit: {label_prov}-{label_city} (+{amt:.2f})")
        else:
            reasons.append(f"dest_adjustment_hit: {label_prov} (+{amt:.2f})")

    return da_details, float(da_sum)
