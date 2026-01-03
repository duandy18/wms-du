# app/services/shipping_quote/calc.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember

from .matchers import _match_bracket, _match_zone
from .pricing import _calc_base_amount
from .surcharges import _calc_surcharge_amount, _cond_match
from .types import Dest, _utcnow
from .weight import _compute_billable_weight_kg


def _scheme_is_effective(sch: ShippingProviderPricingScheme, now: datetime) -> bool:
    if not bool(sch.active):
        return False
    if sch.effective_from is not None and sch.effective_from > now:
        return False
    if sch.effective_to is not None and sch.effective_to < now:
        return False
    return True


def calc_quote(
    db: Session,
    scheme_id: int,
    dest: Dest,
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    flags: Optional[List[str]],
) -> Dict[str, Any]:
    sch = db.get(ShippingProviderPricingScheme, scheme_id)
    if not sch:
        raise ValueError("scheme not found")

    now = _utcnow()
    if not _scheme_is_effective(sch, now):
        raise ValueError("scheme not effective (inactive or out of date range)")

    zones = db.query(ShippingProviderZone).filter(ShippingProviderZone.scheme_id == scheme_id).all()
    zone_ids = [z.id for z in zones]

    members: List[ShippingProviderZoneMember] = []
    brackets: List[ShippingProviderZoneBracket] = []
    if zone_ids:
        members = (
            db.query(ShippingProviderZoneMember)
            .filter(ShippingProviderZoneMember.zone_id.in_(zone_ids))
            .all()
        )
        brackets = (
            db.query(ShippingProviderZoneBracket)
            .filter(ShippingProviderZoneBracket.zone_id.in_(zone_ids))
            .all()
        )

    surcharges = (
        db.query(ShippingProviderSurcharge)
        .filter(
            ShippingProviderSurcharge.scheme_id == scheme_id,
            ShippingProviderSurcharge.active.is_(True),
        )
        .order_by(ShippingProviderSurcharge.id.asc())
        .all()
    )

    weight_info = _compute_billable_weight_kg(real_weight_kg, dims_cm, sch.billable_weight_rule)
    bw = float(weight_info["billable_weight_kg"])
    scheme_rounding = sch.billable_weight_rule.get("rounding") if sch.billable_weight_rule else None

    zone, hit_member = _match_zone(zones, members, dest)
    if not zone:
        raise ValueError("no matching zone")

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
    # ✅ 口径统一：左开右闭 (mn, mx]
    reasons.append(f"bracket_match: ({mn}kg, {('inf' if mx is None else mx)}kg] (billable={bw}kg)")

    base_amt, base_detail = _calc_base_amount(bracket, bw, scheme_rounding)

    # manual quote 分支
    if base_detail.get("kind") == "manual_quote":
        reasons.append("base_pricing: manual_quote_required")

        breakdown = {
            "base": {"amount": float(base_amt), **base_detail},
            "surcharges": [],
            "summary": {"base_amount": float(base_amt), "surcharge_amount": 0.0, "total_amount": None},
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

    # surcharge
    s_details: List[Dict[str, Any]] = []
    s_sum = 0.0
    for s in surcharges:
        if not _cond_match(s.condition_json or {}, dest, flags or []):
            continue
        amt, detail = _calc_surcharge_amount(s.amount_json or {}, bw, scheme_rounding)
        s_sum += float(amt)
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

    total = float(base_amt) + float(s_sum)
    reasons.append(f"total={total:.2f} {sch.currency}")

    breakdown = {
        "base": {"amount": float(base_amt), **base_detail},
        "surcharges": s_details,
        "summary": {"base_amount": float(base_amt), "surcharge_amount": float(s_sum), "total_amount": float(total)},
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
