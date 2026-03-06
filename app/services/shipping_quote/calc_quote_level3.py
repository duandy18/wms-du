# app/services/shipping_quote/calc_quote_level3.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge

from .matchers import _match_destination_group, _match_pricing_matrix
from .pricing import _calc_base_amount
from .surcharge_select import select_surcharges_city_wins
from .surcharges import _calc_surcharge_amount, _cond_match
from .types import Dest
from .weight import _compute_billable_weight_kg

JsonObject = Dict[str, object]


def _to_hit_member_out_level3(
    hit_member: ShippingProviderDestinationGroupMember | None,
) -> JsonObject | None:
    if hit_member is None:
        return None

    scope = str(hit_member.scope or "").strip().lower()
    if scope == "city":
        value = hit_member.city_name or hit_member.city_code or ""
    else:
        value = hit_member.province_name or hit_member.province_code or ""

    return {
        "id": hit_member.id,
        "level": scope,
        "value": value,
        "province_code": hit_member.province_code,
        "city_code": hit_member.city_code,
        "province_name": hit_member.province_name,
        "city_name": hit_member.city_name,
    }


def _build_level3_quote_result(
    *,
    sch: ShippingProviderPricingScheme,
    quote_status: str,
    reasons: List[str],
    dest: Dest,
    weight_info: JsonObject,
    group_out: JsonObject,
    matrix_out: JsonObject,
    breakdown: JsonObject,
    total_amount: float | None,
) -> JsonObject:
    # 为了不改 API 合同，这里继续沿用 zone / bracket 键名
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
        "zone": group_out,
        "bracket": matrix_out,
        "breakdown": breakdown,
        "total_amount": total_amount,
    }


def calc_quote_level3(
    *,
    db: Session,
    sch: ShippingProviderPricingScheme,
    dest: Dest,
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    flags: Optional[List[str]],
) -> JsonObject:
    scheme_id = int(sch.id)

    groups = (
        db.query(ShippingProviderDestinationGroup)
        .filter(ShippingProviderDestinationGroup.scheme_id == scheme_id)
        .all()
    )
    group_ids = [g.id for g in groups]

    members: List[ShippingProviderDestinationGroupMember] = []
    matrix_rows: List[ShippingProviderPricingMatrix] = []

    if group_ids:
        members = (
            db.query(ShippingProviderDestinationGroupMember)
            .filter(ShippingProviderDestinationGroupMember.group_id.in_(group_ids))
            .all()
        )
        matrix_rows = (
            db.query(ShippingProviderPricingMatrix)
            .filter(ShippingProviderPricingMatrix.group_id.in_(group_ids))
            .all()
        )

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

    weight_info = _compute_billable_weight_kg(
        real_weight_kg,
        dims_cm,
        sch.billable_weight_rule,
    )
    bw = float(weight_info["billable_weight_kg"])

    scheme_rounding = sch.billable_weight_rule.get("rounding") if sch.billable_weight_rule else None
    weight_info["rounding"] = scheme_rounding
    weight_info["rounding_source"] = "scheme.billable_weight_rule.rounding"

    group, hit_member = _match_destination_group(groups, members, dest)
    if not group:
        raise ValueError("no matching destination group")

    group_matrix = [r for r in matrix_rows if r.group_id == group.id and bool(r.active)]
    row = _match_pricing_matrix(group_matrix, bw)
    if not row:
        raise ValueError("no matching pricing matrix")

    reasons: List[str] = ["quote_engine: level3"]
    if hit_member is not None:
        reasons.append(
            "group_match: "
            f"group={group.name} "
            f"member({(hit_member.scope or '').lower()}="
            f"{hit_member.city_name or hit_member.city_code or hit_member.province_name or hit_member.province_code})"
        )
    else:
        reasons.append(f"group_match: group={group.name} (fallback)")

    mn = float(row.min_kg)
    mx = float(row.max_kg) if row.max_kg is not None else None
    reasons.append(f"matrix_match: ({mn}kg, {('inf' if mx is None else mx)}kg] (billable={bw}kg)")

    base_amt, base_detail = _calc_base_amount(row, bw, scheme_rounding)

    group_out: JsonObject = {
        "id": group.id,
        "name": group.name,
        "hit_member": _to_hit_member_out_level3(hit_member),
        "source": "level3",
    }
    matrix_out: JsonObject = {
        "id": row.id,
        "min_kg": float(row.min_kg),
        "max_kg": None if row.max_kg is None else float(row.max_kg),
        "pricing_mode": str(row.pricing_mode),
        "flat_amount": None if row.flat_amount is None else float(row.flat_amount),
        "base_amount": None if row.base_amount is None else float(row.base_amount),
        "rate_per_kg": None if row.rate_per_kg is None else float(row.rate_per_kg),
        "base_kg": None if getattr(row, "base_kg", None) is None else float(row.base_kg),
        "source": "level3",
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

        return _build_level3_quote_result(
            sch=sch,
            quote_status="MANUAL_REQUIRED",
            reasons=reasons,
            dest=dest,
            weight_info=weight_info,
            group_out=group_out,
            matrix_out=matrix_out,
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

    return _build_level3_quote_result(
        sch=sch,
        quote_status="OK",
        reasons=reasons,
        dest=dest,
        weight_info=weight_info,
        group_out=group_out,
        matrix_out=matrix_out,
        breakdown=breakdown,
        total_amount=total,
    )
