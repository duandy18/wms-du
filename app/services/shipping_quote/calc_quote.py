# app/services/shipping_quote/calc_quote.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember

from .calc_core import check_scheme_warehouse_allowed, scheme_is_effective
from .calc_quote_level3 import calc_quote_level3
from .matchers import _match_bracket, _match_zone
from .pricing import _calc_base_amount
from .surcharge_select import select_surcharges_city_wins
from .surcharges import _calc_surcharge_amount, _cond_match
from .types import Dest, _utcnow
from .weight import _compute_billable_weight_kg

JsonObject = Dict[str, object]


def _to_hit_member_out_legacy(hit_member: ShippingProviderZoneMember | None) -> JsonObject | None:
    if hit_member is None:
        return None
    return {
        "id": hit_member.id,
        "level": hit_member.level,
        "value": hit_member.value,
    }


def _build_legacy_quote_result(
    *,
    sch: ShippingProviderPricingScheme,
    quote_status: str,
    reasons: List[str],
    dest: Dest,
    weight_info: JsonObject,
    zone_out: JsonObject,
    bracket_out: JsonObject,
    breakdown: JsonObject,
    total_amount: float | None,
) -> JsonObject:
    return {
        "ok": True,
        "scheme_id": sch.id,
        "shipping_provider_id": sch.shipping_provider_id,
        "currency": sch.currency,
        "quote_status": quote_status,
        "reasons": reasons,
        "dest": {
            "province": dest.province,
            "city": dest.city,
            "district": dest.district,
            "province_code": dest.province_code,
            "city_code": dest.city_code,
        },
        "weight": weight_info,
        "zone": zone_out,
        "bracket": bracket_out,
        "breakdown": breakdown,
        "total_amount": total_amount,
    }


def _calc_quote_legacy(
    *,
    db: Session,
    sch: ShippingProviderPricingScheme,
    dest: Dest,
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    flags: Optional[List[str]],
) -> JsonObject:
    scheme_id = int(sch.id)

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
        .order_by(
            ShippingProviderSurcharge.priority.asc(),
            ShippingProviderSurcharge.id.asc(),
        )
        .all()
    )

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

    reasons: List[str] = ["quote_engine: legacy"]
    if hit_member is not None:
        reasons.append(f"zone_match: zone={zone.name} member({(hit_member.level or '').lower()}={hit_member.value})")
    else:
        reasons.append(f"zone_match: zone={zone.name} (fallback)")

    mn = float(bracket.min_kg)
    mx = float(bracket.max_kg) if bracket.max_kg is not None else None
    reasons.append(f"bracket_match: ({mn}kg, {('inf' if mx is None else mx)}kg] (billable={bw}kg)")

    base_amt, base_detail = _calc_base_amount(bracket, bw, scheme_rounding)

    zone_out: JsonObject = {
        "id": zone.id,
        "name": zone.name,
        "hit_member": _to_hit_member_out_legacy(hit_member),
        "source": "legacy",
    }
    bracket_out: JsonObject = {
        "id": bracket.id,
        "min_kg": float(bracket.min_kg),
        "max_kg": None if bracket.max_kg is None else float(bracket.max_kg),
        "pricing_mode": str(bracket.pricing_mode),
        "flat_amount": None if bracket.flat_amount is None else float(bracket.flat_amount),
        "base_amount": None if bracket.base_amount is None else float(bracket.base_amount),
        "rate_per_kg": None if bracket.rate_per_kg is None else float(bracket.rate_per_kg),
        "base_kg": None if getattr(bracket, "base_kg", None) is None else float(bracket.base_kg),
        "source": "legacy",
    }

    if isinstance(base_detail, dict) and base_detail.get("kind") == "manual_quote":
        reasons.append("base_pricing: manual_quote_required")

        breakdown: JsonObject = {
            "base": {"amount": float(base_amt), **base_detail},
            "surcharges": [],
            "summary": {
                "base_amount": float(base_amt),
                "surcharge_amount": 0.0,
                "extra_amount": 0.0,
                "total_amount": None,
            },
        }

        return _build_legacy_quote_result(
            sch=sch,
            quote_status="MANUAL_REQUIRED",
            reasons=reasons,
            dest=dest,
            weight_info=weight_info,
            zone_out=zone_out,
            bracket_out=bracket_out,
            breakdown=breakdown,
            total_amount=None,
        )

    matched: List[ShippingProviderSurcharge] = []
    for s in surcharges:
        if _cond_match(s, dest, flags or []):
            matched.append(s)

    final_surcharges = select_surcharges_city_wins(
        matched=matched,
        dest=dest,
        reasons=reasons,
    )

    s_details: List[JsonObject] = []
    surcharge_sum = 0.0
    for s in final_surcharges:
        amt, detail = _calc_surcharge_amount(s, bw, scheme_rounding)
        surcharge_sum += float(amt)
        s_details.append(
            {
                "id": s.id,
                "name": s.name,
                "priority": int(getattr(s, "priority", 100) or 100),
                "scope": str(getattr(s, "scope", "always") or "always"),
                "stackable": bool(getattr(s, "stackable", True)),
                "province_code": getattr(s, "province_code", None),
                "city_code": getattr(s, "city_code", None),
                "province_name": getattr(s, "province_name", None),
                "city_name": getattr(s, "city_name", None),
                "amount": float(amt),
                "detail": detail,
            }
        )
        reasons.append(f"surcharge_hit: {s.name} (+{float(amt):.2f})")

    extra_sum = float(surcharge_sum)
    total = float(base_amt) + float(extra_sum)
    reasons.append(f"total={total:.2f} {sch.currency}")

    breakdown = {
        "base": {"amount": float(base_amt), **(base_detail if isinstance(base_detail, dict) else {})},
        "surcharges": s_details,
        "summary": {
            "base_amount": float(base_amt),
            "surcharge_amount": float(surcharge_sum),
            "extra_amount": float(extra_sum),
            "total_amount": float(total),
        },
    }

    return _build_legacy_quote_result(
        sch=sch,
        quote_status="OK",
        reasons=reasons,
        dest=dest,
        weight_info=weight_info,
        zone_out=zone_out,
        bracket_out=bracket_out,
        breakdown=breakdown,
        total_amount=total,
    )


def _has_level3_rows(db: Session, scheme_id: int) -> bool:
    group_ids = [
        int(x[0])
        for x in (
            db.query(ShippingProviderDestinationGroup.id)
            .filter(ShippingProviderDestinationGroup.scheme_id == int(scheme_id))
            .all()
        )
    ]
    if not group_ids:
        return False

    has_matrix = (
        db.query(ShippingProviderPricingMatrix.id)
        .filter(ShippingProviderPricingMatrix.group_id.in_(group_ids))
        .limit(1)
        .first()
        is not None
    )
    return bool(has_matrix)


def _float_or_none(v: object) -> float | None:
    if v is None:
        return None
    return float(v)


def _compare_quote_results(
    legacy_result: JsonObject,
    level3_result: JsonObject,
) -> List[str]:
    diffs: List[str] = []

    if str(legacy_result.get("quote_status")) != str(level3_result.get("quote_status")):
        diffs.append("quote_status")

    lt = _float_or_none(legacy_result.get("total_amount"))
    nt = _float_or_none(level3_result.get("total_amount"))
    if lt is None and nt is not None:
        diffs.append("total_amount")
    elif lt is not None and nt is None:
        diffs.append("total_amount")
    elif lt is not None and nt is not None and abs(lt - nt) > 1e-9:
        diffs.append("total_amount")

    lz = legacy_result.get("zone") or {}
    nz = level3_result.get("zone") or {}
    if str(lz.get("name") or "") != str(nz.get("name") or ""):
        diffs.append("zone.name")

    lb = legacy_result.get("bracket") or {}
    nb = level3_result.get("bracket") or {}

    if str(lb.get("pricing_mode") or "") != str(nb.get("pricing_mode") or ""):
        diffs.append("bracket.pricing_mode")

    for k in ("min_kg", "max_kg", "flat_amount", "base_amount", "rate_per_kg", "base_kg"):
        lv = _float_or_none(lb.get(k))
        nv = _float_or_none(nb.get(k))
        if lv is None and nv is None:
            continue
        if lv is None or nv is None or abs(lv - nv) > 1e-9:
            diffs.append(f"bracket.{k}")

    lsum = ((legacy_result.get("breakdown") or {}).get("summary") or {})
    nsum = ((level3_result.get("breakdown") or {}).get("summary") or {})
    for k in ("base_amount", "surcharge_amount", "extra_amount", "total_amount"):
        lv = _float_or_none(lsum.get(k))
        nv = _float_or_none(nsum.get(k))
        if lv is None and nv is None:
            continue
        if lv is None or nv is None or abs(lv - nv) > 1e-9:
            diffs.append(f"breakdown.summary.{k}")

    ls = (legacy_result.get("breakdown") or {}).get("surcharges") or []
    ns = (level3_result.get("breakdown") or {}).get("surcharges") or []
    if len(ls) != len(ns):
        diffs.append("breakdown.surcharges.len")
    else:
        for i, (a, b) in enumerate(zip(ls, ns)):
            an = str((a or {}).get("name") or "")
            bn = str((b or {}).get("name") or "")
            aa = _float_or_none((a or {}).get("amount"))
            ba = _float_or_none((b or {}).get("amount"))
            if an != bn:
                diffs.append(f"breakdown.surcharges[{i}].name")
            if aa is None or ba is None or abs(aa - ba) > 1e-9:
                diffs.append(f"breakdown.surcharges[{i}].amount")

    seen: set[str] = set()
    out: List[str] = []
    for d in diffs:
        if d in seen:
            continue
        seen.add(d)
        out.append(d)
    return out


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

    check_scheme_warehouse_allowed(db, scheme_id=int(scheme_id), warehouse_id=int(warehouse_id))

    legacy_result = _calc_quote_legacy(
        db=db,
        sch=sch,
        dest=dest,
        real_weight_kg=real_weight_kg,
        dims_cm=dims_cm,
        flags=flags,
    )

    if not _has_level3_rows(db, int(scheme_id)):
        return legacy_result

    try:
        level3_result = calc_quote_level3(
            db=db,
            sch=sch,
            dest=dest,
            real_weight_kg=real_weight_kg,
            dims_cm=dims_cm,
            flags=flags,
        )
    except Exception as e:
        reasons = list(legacy_result.get("reasons") or [])
        reasons.append(f"level3_compare_error: {e}")
        legacy_result["reasons"] = reasons
        return legacy_result

    diffs = _compare_quote_results(legacy_result, level3_result)
    reasons = list(legacy_result.get("reasons") or [])
    if not diffs:
        reasons.append("level3_compare: match")
    else:
        reasons.append(f"level3_compare_mismatch: {', '.join(diffs)}")
    legacy_result["reasons"] = reasons

    return legacy_result
