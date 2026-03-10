# app/services/shipping_quote/calc_quote_level3.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, selectinload

from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge_config import ShippingProviderSurchargeConfig
from app.models.shipping_provider_surcharge_config_city import ShippingProviderSurchargeConfigCity

from .matchers import _match_destination_group, _match_pricing_matrix
from .pricing import _calc_base_amount
from .types import Dest
from .weight import _compute_billable_weight_kg

JsonObject = Dict[str, object]


def _s(v: object | None) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _to_hit_member_out_level3(
    hit_member: ShippingProviderDestinationGroupMember | None,
) -> JsonObject | None:
    if hit_member is None:
        return None

    value = hit_member.province_name or hit_member.province_code or ""

    return {
        "id": int(hit_member.id),
        "level": "province",
        "value": value,
        "province_code": hit_member.province_code,
        "province_name": hit_member.province_name,
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
    return {
        "ok": True,
        "scheme_id": int(sch.id),
        "shipping_provider_id": int(sch.shipping_provider_id),
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
        "destination_group": group_out,
        "pricing_matrix": matrix_out,
        "breakdown": breakdown,
        "total_amount": total_amount,
    }


def _scheme_rounding_rule(sch: ShippingProviderPricingScheme) -> JsonObject | None:
    rounding_mode = getattr(sch, "rounding_mode", None)
    rounding_step_kg = getattr(sch, "rounding_step_kg", None)

    mode = str(rounding_mode or "").strip().lower()
    if not mode or mode == "none":
        return None

    step = None if rounding_step_kg is None else float(rounding_step_kg)
    if step is None or step <= 0:
        return None

    return {
        "mode": mode,
        "step_kg": step,
    }


def _scheme_billable_weight_rule(sch: ShippingProviderPricingScheme) -> JsonObject | None:
    strategy = str(getattr(sch, "billable_weight_strategy", "") or "").strip().lower()
    volume_divisor = getattr(sch, "volume_divisor", None)
    min_billable_weight_kg = getattr(sch, "min_billable_weight_kg", None)

    rule: Dict[str, Any] = {}

    if strategy == "max_actual_volume":
        if volume_divisor is None:
            raise ValueError("scheme billable_weight_strategy=max_actual_volume requires volume_divisor")
        rule["volume_divisor"] = int(volume_divisor)

    if min_billable_weight_kg is not None:
        rule["min_billable_weight_kg"] = float(min_billable_weight_kg)

    rounding = _scheme_rounding_rule(sch)
    if rounding is not None:
        rule["rounding"] = rounding

    return rule or None


def _matrix_range(row: ShippingProviderPricingMatrix) -> Tuple[Decimal, Optional[Decimal]]:
    mr = getattr(row, "module_range", None)
    if mr is None:
        raise ValueError(f"pricing_matrix row missing module_range (row_id={getattr(row, 'id', None)})")
    return mr.min_kg, mr.max_kg


def _province_match(
    cfg: ShippingProviderSurchargeConfig,
    dest: Dest,
) -> bool:
    row_prov_code = _s(getattr(cfg, "province_code", None))
    row_prov_name = _s(getattr(cfg, "province_name", None))
    dest_prov_code = _s(getattr(dest, "province_code", None))
    dest_prov_name = _s(getattr(dest, "province", None))

    if row_prov_code and dest_prov_code:
        return row_prov_code == dest_prov_code
    if row_prov_name and dest_prov_name:
        return row_prov_name == dest_prov_name
    return False


def _city_match(
    row: ShippingProviderSurchargeConfigCity,
    dest: Dest,
) -> bool:
    row_city_code = _s(getattr(row, "city_code", None))
    row_city_name = _s(getattr(row, "city_name", None))
    dest_city_code = _s(getattr(dest, "city_code", None))
    dest_city_name = _s(getattr(dest, "city", None))

    if row_city_code and dest_city_code:
        return row_city_code == dest_city_code
    if row_city_name and dest_city_name:
        return row_city_name == dest_city_name
    return False


def _select_surcharge_from_configs(
    *,
    configs: List[ShippingProviderSurchargeConfig],
    dest: Dest,
    reasons: List[str],
) -> tuple[
    ShippingProviderSurchargeConfig | None,
    ShippingProviderSurchargeConfigCity | None,
    float,
    JsonObject | None,
]:
    matched_configs = [cfg for cfg in configs if bool(getattr(cfg, "active", False)) and _province_match(cfg, dest)]
    if not matched_configs:
        return None, None, 0.0, None

    cfg = sorted(matched_configs, key=lambda x: int(x.id))[0]
    province_mode = str(getattr(cfg, "province_mode", "province") or "province").strip().lower()

    if province_mode == "province":
        amt = float(getattr(cfg, "fixed_amount", 0) or 0.0)
        reasons.append(
            f"surcharge_select: province>{getattr(cfg, 'province_name', None) or getattr(cfg, 'province_code', None) or cfg.id}"
        )
        return cfg, None, amt, {"kind": "fixed", "amount": amt}

    city_rows = [
        row
        for row in (getattr(cfg, "cities", []) or [])
        if bool(getattr(row, "active", False)) and _city_match(row, dest)
    ]
    if not city_rows:
        return cfg, None, 0.0, None

    city_row = sorted(city_rows, key=lambda x: int(x.id))[0]
    amt = float(getattr(city_row, "fixed_amount", 0) or 0.0)
    reasons.append(
        "surcharge_select: city>"
        f"{getattr(cfg, 'province_name', None) or getattr(cfg, 'province_code', None)}-"
        f"{getattr(city_row, 'city_name', None) or getattr(city_row, 'city_code', None)}"
    )
    return cfg, city_row, amt, {"kind": "fixed", "amount": amt}


def calc_quote_level3(
    *,
    db: Session,
    sch: ShippingProviderPricingScheme,
    dest: Dest,
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    flags: Optional[List[str]],
) -> JsonObject:
    _ = flags

    scheme_id = int(sch.id)

    groups = (
        db.query(ShippingProviderDestinationGroup)
        .filter(ShippingProviderDestinationGroup.scheme_id == scheme_id)
        .all()
    )
    group_ids = [int(g.id) for g in groups]

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
            .options(selectinload(ShippingProviderPricingMatrix.module_range))
            .filter(ShippingProviderPricingMatrix.group_id.in_(group_ids))
            .all()
        )

    surcharge_configs = (
        db.query(ShippingProviderSurchargeConfig)
        .options(selectinload(ShippingProviderSurchargeConfig.cities))
        .filter(ShippingProviderSurchargeConfig.scheme_id == scheme_id)
        .order_by(ShippingProviderSurchargeConfig.id.asc())
        .all()
    )

    billable_weight_rule = _scheme_billable_weight_rule(sch)
    weight_info = _compute_billable_weight_kg(
        real_weight_kg,
        dims_cm,
        billable_weight_rule,
    )
    bw = float(weight_info["billable_weight_kg"])

    scheme_rounding = _scheme_rounding_rule(sch)
    weight_info["rounding"] = scheme_rounding
    weight_info["rounding_source"] = "scheme.rounding_mode/rounding_step_kg"

    group, hit_member = _match_destination_group(groups, members, dest)
    if not group:
        raise ValueError("no matching destination group")

    group_matrix = [r for r in matrix_rows if int(r.group_id) == int(group.id) and bool(r.active)]

    for r in group_matrix:
        mn, mx = _matrix_range(r)
        setattr(r, "min_kg", mn)
        setattr(r, "max_kg", mx)

    row = _match_pricing_matrix(group_matrix, bw)
    if not row:
        raise ValueError("no matching pricing matrix")

    row_min_kg, row_max_kg = _matrix_range(row)

    reasons: List[str] = []
    if hit_member is not None:
        reasons.append(
            "group_match: "
            f"group={group.name} "
            f"member(province={hit_member.province_name or hit_member.province_code})"
        )
    else:
        reasons.append(f"group_match: group={group.name} (fallback)")

    mn = float(row_min_kg)
    mx = float(row_max_kg) if row_max_kg is not None else None
    reasons.append(f"matrix_match: [{mn}kg, {('inf' if mx is None else mx)}kg) (billable={bw}kg)")

    base_amt, base_detail = _calc_base_amount(row, bw, scheme_rounding)

    group_out: JsonObject = {
        "id": int(group.id),
        "name": group.name,
        "hit_member": _to_hit_member_out_level3(hit_member),
        "source": "level3",
    }
    matrix_out: JsonObject = {
        "id": int(row.id),
        "module_range_id": int(row.module_range_id),
        "min_kg": float(row_min_kg),
        "max_kg": None if row_max_kg is None else float(row_max_kg),
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

    chosen_cfg, chosen_city, surcharge_amt, surcharge_detail = _select_surcharge_from_configs(
        configs=surcharge_configs,
        dest=dest,
        reasons=reasons,
    )

    s_details: List[JsonObject] = []
    surcharge_sum = 0.0

    if chosen_cfg is not None and surcharge_detail is not None:
        surcharge_sum += float(surcharge_amt)

        s_details.append(
            {
                "id": int(chosen_city.id) if chosen_city is not None else int(chosen_cfg.id),
                "name": (
                    f"{chosen_cfg.province_name or chosen_cfg.province_code}-{chosen_city.city_name or chosen_city.city_code}"
                    if chosen_city is not None
                    else str(chosen_cfg.province_name or chosen_cfg.province_code or chosen_cfg.id)
                ),
                "scope": "city" if chosen_city is not None else "province",
                "province_code": getattr(chosen_cfg, "province_code", None),
                "city_code": getattr(chosen_city, "city_code", None) if chosen_city is not None else None,
                "province_name": getattr(chosen_cfg, "province_name", None),
                "city_name": getattr(chosen_city, "city_name", None) if chosen_city is not None else None,
                "amount": float(surcharge_amt),
                "detail": surcharge_detail,
            }
        )
        reasons.append(f"surcharge_hit: +{float(surcharge_amt):.2f}")

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
