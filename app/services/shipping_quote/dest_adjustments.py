# app/services/shipping_quote/dest_adjustments.py
from __future__ import annotations

from typing import Dict, List

from app.models.pricing_scheme_dest_adjustment import PricingSchemeDestAdjustment
from .types import Dest

JsonObject = Dict[str, object]


def _norm(v: object | None) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _is_municipality_province_code(prov_code: str) -> bool:
    # ✅ 直辖市省码（GB2260）：北京/天津/上海/重庆
    pc = _norm(prov_code)
    return pc in {"110000", "120000", "310000", "500000"}


def _municipality_city_code_from_prov_code(prov_code: str) -> str:
    # ✅ 显式映射：省码 xx0000 → 市码 xx0100（唯一市口径）
    # 110000 → 110100, 120000 → 120100, 310000 → 310100, 500000 → 500100
    pc = _norm(prov_code)
    try:
        n = int(pc)
    except Exception:
        return ""
    return str(n + 100).zfill(6)


def read_dest_keys(dest: Dest) -> tuple[str, str]:
    """
    ✅ 优先使用 code（province_code/city_code），没有则 fallback 到 name（province/city）。
    ✅ 兼容期策略：不强依赖 Dest 已升级。
    ✅ 直辖市友好：若缺 city_code 且 prov_code 是直辖市，则可推导唯一 city_code（xx0100）
    """
    prov_code = getattr(dest, "province_code", None)
    city_code = getattr(dest, "city_code", None)

    prov_name = (dest.province or "").strip()
    city_name = (dest.city or "").strip()

    prov_code_s = _norm(prov_code)
    city_code_s = _norm(city_code)

    # ✅ 直辖市：若未提供 city_code，但提供了 prov_code，可推导唯一市 code（用于 city-scope 命中/解释）
    if prov_code_s and _is_municipality_province_code(prov_code_s) and not city_code_s:
        city_code_s = _municipality_city_code_from_prov_code(prov_code_s)

    prov_key = prov_code_s or prov_name
    city_key = city_code_s or city_name
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

    ✅ 直辖市“按省配置”友好策略：
    - 允许 dest 只给 name（如“北京市”）时，也能命中配置行的 province_name（不强迫操作者/前端必须传 code）
    - 若同时存在 city-scope 规则，仍然 city wins（不改变主裁决）
    """
    prov_key, city_key = read_dest_keys(dest)
    if not prov_key:
        return []

    hit_province: List[PricingSchemeDestAdjustment] = []
    hit_city: List[PricingSchemeDestAdjustment] = []

    for r in rows:
        if not bool(r.active):
            continue

        # ✅ 兼容：配置行的 province 可能体现在 province_code / province_name / legacy province 字段
        r_prov_key = _norm(r.province_code) or _norm(r.province_name) or _norm(r.province)
        if r_prov_key != prov_key:
            continue

        sc = _norm(r.scope).lower()
        if sc == "province":
            hit_province.append(r)
        elif sc == "city":
            # ✅ 兼容：配置行的 city 可能体现在 city_code / city_name / legacy city 字段
            r_city_key = _norm(r.city_code) or _norm(r.city_name) or _norm(r.city)
            if city_key and r_city_key == city_key:
                hit_city.append(r)

    chosen: List[PricingSchemeDestAdjustment] = []

    if hit_city:
        chosen.extend(sorted(hit_city, key=lambda x: int(x.id)))
        if hit_province:
            # ✅ 白盒：明确说明 province 被抑制
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
        if (_norm(r.scope).lower()) == "city":
            reasons.append(f"dest_adjustment_hit: {label_prov}-{label_city} (+{amt:.2f})")
        else:
            reasons.append(f"dest_adjustment_hit: {label_prov} (+{amt:.2f})")

    return da_details, float(da_sum)
