# app/services/shipping_quote/calc_quote.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.pricing_scheme_dest_adjustment import PricingSchemeDestAdjustment
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember

from .calc_core import check_scheme_warehouse_allowed, scheme_is_effective
from .matchers import _match_bracket, _match_zone
from .pricing import _calc_base_amount
from .surcharge_select import select_surcharges_city_wins
from .surcharges import _calc_surcharge_amount, _cond_match
from .types import Dest, _utcnow
from .weight import _compute_billable_weight_kg

JsonObject = Dict[str, object]


def _match_dest_adjustments(
    rows: List[PricingSchemeDestAdjustment],
    dest: Dest,
    reasons: List[str],
) -> List[PricingSchemeDestAdjustment]:
    """
    ✅ 目的地附加费命中（结构化事实）：
    - 先找同省 province 命中
    - 再找同省同市 city 命中
    - 若 city 命中，则 province 被 suppressed（记录 reasons）
    - 理论上 service 层已保证 active 互斥，但算价层仍做“保险式解释”，防止脏数据/历史数据影响
    """
    prov = (dest.province or "").strip()
    city = (dest.city or "").strip()

    if not prov:
        return []

    hit_province: List[PricingSchemeDestAdjustment] = []
    hit_city: List[PricingSchemeDestAdjustment] = []

    for r in rows:
        if not bool(r.active):
            continue
        if (r.province or "").strip() != prov:
            continue
        sc = (r.scope or "").strip().lower()
        if sc == "province":
            hit_province.append(r)
        elif sc == "city":
            if city and (r.city or "").strip() == city:
                hit_city.append(r)

    # 约束下正常情况：最多命中 1 条（unique key + 互斥）
    chosen: List[PricingSchemeDestAdjustment] = []
    if hit_city:
        # city wins
        chosen.extend(sorted(hit_city, key=lambda x: int(x.id)))
        if hit_province:
            reasons.append(f"dest_adjustment_suppressed: province={prov} (city wins)")
    else:
        chosen.extend(sorted(hit_province, key=lambda x: int(x.id)))

    return chosen


def calc_quote(
    db: Session,
    scheme_id: int,
    warehouse_id: int,
    dest: Dest,
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    flags: Optional[List[str]],
) -> JsonObject:
    sch = db.get(ShippingProviderPricingScheme, scheme_id)
    if not sch:
        raise ValueError("scheme not found")

    now = _utcnow()
    if not scheme_is_effective(sch, now):
        raise ValueError("scheme not effective (inactive or out of date range)")

    # ✅ 合同硬化：先验起运仓边界（不允许隐式全仓可用）
    check_scheme_warehouse_allowed(db, scheme_id=int(scheme_id), warehouse_id=int(warehouse_id))

    zones = db.query(ShippingProviderZone).filter(ShippingProviderZone.scheme_id == scheme_id).all()
    zone_ids = [z.id for z in zones]

    members: List[ShippingProviderZoneMember] = []
    brackets: List[ShippingProviderZoneBracket] = []
    if zone_ids:
        members = db.query(ShippingProviderZoneMember).filter(ShippingProviderZoneMember.zone_id.in_(zone_ids)).all()
        brackets = db.query(ShippingProviderZoneBracket).filter(ShippingProviderZoneBracket.zone_id.in_(zone_ids)).all()

    surcharges = (
        db.query(ShippingProviderSurcharge)
        .filter(
            ShippingProviderSurcharge.scheme_id == scheme_id,
            ShippingProviderSurcharge.active.is_(True),
        )
        .order_by(ShippingProviderSurcharge.id.asc())
        .all()
    )

    # ✅ 新：目的地附加费（结构化事实模型）
    dest_adjustments_all = (
        db.query(PricingSchemeDestAdjustment)
        .filter(
            PricingSchemeDestAdjustment.scheme_id == scheme_id,
            PricingSchemeDestAdjustment.active.is_(True),
        )
        .order_by(PricingSchemeDestAdjustment.id.asc())
        .all()
    )

    # ✅ 计费重（唯一取整点）
    weight_info = _compute_billable_weight_kg(real_weight_kg, dims_cm, sch.billable_weight_rule)
    bw = float(weight_info["billable_weight_kg"])

    scheme_rounding = sch.billable_weight_rule.get("rounding") if sch.billable_weight_rule else None
    weight_info["rounding"] = scheme_rounding
    weight_info["rounding_source"] = "scheme.billable_weight_rule.rounding"

    zone, hit_member = _match_zone(zones, members, dest)
    if not zone:
        raise ValueError("no matching zone")

    if getattr(zone, "segment_template_id", None) is None:
        raise ValueError("zone template required")

    zone_brackets = [b for b in brackets if b.zone_id == zone.id and b.active]
    bracket = _match_bracket(zone_brackets, bw)
    if not bracket:
        raise ValueError("no matching bracket")

    reasons: List[str] = []
    if hit_member is not None:
        reasons.append(f"zone_match: zone={zone.name} member({(hit_member.level or '').lower()}={hit_member.value})")
    else:
        reasons.append(f"zone_match: zone={zone.name} (fallback)")

    mn = float(bracket.min_kg)
    mx = float(bracket.max_kg) if bracket.max_kg is not None else None
    reasons.append(f"bracket_match: ({mn}kg, {('inf' if mx is None else mx)}kg] (billable={bw}kg)")

    # ✅ 目的地附加费命中（city > province）
    chosen_dest_adjustments = _match_dest_adjustments(dest_adjustments_all, dest, reasons)
    da_details: List[JsonObject] = []
    da_sum = 0.0
    for r in chosen_dest_adjustments:
        amt = float(r.amount)
        da_sum += amt
        da_details.append(
            {
                "id": r.id,
                "scheme_id": r.scheme_id,
                "scope": r.scope,
                "province": r.province,
                "city": r.city,
                "amount": float(amt),
                "priority": int(getattr(r, "priority", 100) or 100),
            }
        )
        if (r.scope or "").strip().lower() == "city":
            reasons.append(f"dest_adjustment_hit: {r.province}-{(r.city or '')} (+{amt:.2f})")
        else:
            reasons.append(f"dest_adjustment_hit: {r.province} (+{amt:.2f})")

    base_amt, base_detail = _calc_base_amount(bracket, bw, scheme_rounding)

    if isinstance(base_detail, dict) and base_detail.get("kind") == "manual_quote":
        reasons.append("base_pricing: manual_quote_required")

        legacy_s_sum = 0.0
        extra_sum = float(da_sum) + float(legacy_s_sum)

        breakdown: JsonObject = {
            "base": {"amount": float(base_amt), **base_detail},
            "dest_adjustments": da_details,
            "surcharges": [],
            "summary": {
                "base_amount": float(base_amt),
                "dest_adjustment_amount": float(da_sum),
                "legacy_surcharge_amount": float(legacy_s_sum),
                "extra_amount": float(extra_sum),
                "total_amount": None,
            },
        }

        return {
            "ok": True,
            "scheme_id": sch.id,
            "shipping_provider_id": sch.shipping_provider_id,
            "currency": sch.currency,
            "quote_status": "MANUAL_REQUIRED",
            "reasons": reasons,
            "dest": {"province": dest.province, "city": dest.city, "district": dest.district},
            "weight": weight_info,
            "zone": {
                "id": zone.id,
                "name": zone.name,
                "hit_member": None
                if hit_member is None
                else {"id": hit_member.id, "level": hit_member.level, "value": hit_member.value},
            },
            "bracket": {
                "id": bracket.id,
                "min_kg": float(bracket.min_kg),
                "max_kg": None if bracket.max_kg is None else float(bracket.max_kg),
                "pricing_mode": str(bracket.pricing_mode),
                "flat_amount": None if bracket.flat_amount is None else float(bracket.flat_amount),
                "base_amount": None if bracket.base_amount is None else float(bracket.base_amount),
                "rate_per_kg": None if bracket.rate_per_kg is None else float(bracket.rate_per_kg),
            },
            "breakdown": breakdown,
            "total_amount": None,
        }

    # ✅ legacy surcharge：先找所有命中，再按 city wins 做选择
    matched: List[ShippingProviderSurcharge] = []
    for s in surcharges:
        if _cond_match(s.condition_json or {}, dest, flags or []):
            matched.append(s)

    final_surcharges = select_surcharges_city_wins(matched=matched, dest=dest, reasons=reasons)

    s_details: List[JsonObject] = []
    legacy_s_sum = 0.0
    for s in final_surcharges:
        amt, detail = _calc_surcharge_amount(s.amount_json or {}, bw, scheme_rounding)
        legacy_s_sum += float(amt)
        s_details.append(
            {
                "id": s.id,
                "name": s.name,
                "amount": float(amt),
                "detail": detail,
                "condition": s.condition_json,
            }
        )
        reasons.append(f"surcharge_hit: {s.name} (+{float(amt):.2f})")

    extra_sum = float(da_sum) + float(legacy_s_sum)

    total = float(base_amt) + float(extra_sum)
    reasons.append(f"total={total:.2f} {sch.currency}")

    breakdown: JsonObject = {
        "base": {"amount": float(base_amt), **(base_detail if isinstance(base_detail, dict) else {})},
        "dest_adjustments": da_details,
        "surcharges": s_details,
        "summary": {
            "base_amount": float(base_amt),
            "dest_adjustment_amount": float(da_sum),
            "legacy_surcharge_amount": float(legacy_s_sum),
            "extra_amount": float(extra_sum),
            "total_amount": float(total),
        },
    }

    return {
        "ok": True,
        "scheme_id": sch.id,
        "shipping_provider_id": sch.shipping_provider_id,
        "currency": sch.currency,
        "quote_status": "OK",
        "reasons": reasons,
        "dest": {"province": dest.province, "city": dest.city, "district": dest.district},
        "weight": weight_info,
        "zone": {
            "id": zone.id,
            "name": zone.name,
            "hit_member": None
            if hit_member is None
            else {"id": hit_member.id, "level": hit_member.level, "value": hit_member.value},
        },
        "bracket": {
            "id": bracket.id,
            "min_kg": float(bracket.min_kg),
            "max_kg": None if bracket.max_kg is None else float(bracket.max_kg),
            "pricing_mode": str(bracket.pricing_mode),
            "flat_amount": None if bracket.flat_amount is None else float(bracket.flat_amount),
            "base_amount": None if bracket.base_amount is None else float(bracket.base_amount),
            "rate_per_kg": None if bracket.rate_per_kg is None else float(bracket.rate_per_kg),
        },
        "breakdown": breakdown,
        "total_amount": total,
    }
