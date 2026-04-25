# app/shipping_assist/quote/calc_quote_level3.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .context import (
    QuoteCalcContext,
    QuoteGroupContext,
    QuoteGroupMemberContext,
    QuoteMatrixRowContext,
    QuoteSurchargeConfigContext,
    QuoteSurchargeCityContext,
)
from .pricing import _calc_base_amount
from .types import Dest
from .weight import _compute_billable_weight_kg

JsonObject = Dict[str, object]


def _s(v: object | None) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _to_hit_member_out_level3(
    hit_member: QuoteGroupMemberContext | None,
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
    ctx: QuoteCalcContext,
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
        "template_id": int(ctx.template_id),
        "shipping_provider_id": int(ctx.shipping_provider_id),
        "currency": ctx.currency,
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


def _context_rounding_rule(ctx: QuoteCalcContext) -> JsonObject | None:
    mode = str(ctx.rounding_mode or "").strip().lower()
    if not mode or mode == "none":
        return None

    step = ctx.rounding_step_kg
    if step is None or float(step) <= 0:
        return None

    return {
        "mode": mode,
        "step_kg": float(step),
    }


def _context_billable_weight_rule(ctx: QuoteCalcContext) -> JsonObject | None:
    strategy = str(ctx.billable_weight_strategy or "").strip().lower()
    volume_divisor = ctx.volume_divisor
    min_billable_weight_kg = ctx.min_billable_weight_kg

    rule: Dict[str, object] = {}

    if strategy == "max_actual_volume":
        if volume_divisor is None:
            raise ValueError(
                "quote context billable_weight_strategy=max_actual_volume requires volume_divisor"
            )
        rule["volume_divisor"] = int(volume_divisor)

    if min_billable_weight_kg is not None:
        rule["min_billable_weight_kg"] = float(min_billable_weight_kg)

    rounding = _context_rounding_rule(ctx)
    if rounding is not None:
        rule["rounding"] = rounding

    return rule or None


def _province_match(
    member: QuoteGroupMemberContext,
    dest: Dest,
) -> bool:
    row_prov_code = _s(member.province_code)
    row_prov_name = _s(member.province_name)
    dest_prov_code = _s(getattr(dest, "province_code", None))
    dest_prov_name = _s(getattr(dest, "province", None))

    if row_prov_code and dest_prov_code:
        return row_prov_code == dest_prov_code
    if row_prov_name and dest_prov_name:
        return row_prov_name == dest_prov_name
    return False


def _match_destination_group(
    groups: List[QuoteGroupContext],
    dest: Dest,
) -> tuple[QuoteGroupContext | None, QuoteGroupMemberContext | None]:
    active_groups = [g for g in groups if bool(g.active)]

    for group in active_groups:
        for member in group.members:
            if _province_match(member, dest):
                return group, member

    if active_groups:
        return active_groups[0], None

    return None, None


def _match_pricing_matrix(
    rows: List[QuoteMatrixRowContext],
    billable_weight_kg: float,
) -> QuoteMatrixRowContext | None:
    bw = float(billable_weight_kg)
    active_rows = [r for r in rows if bool(r.active)]

    for row in active_rows:
        min_kg = float(row.min_kg)
        max_kg = None if row.max_kg is None else float(row.max_kg)

        if bw < min_kg:
            continue
        if max_kg is not None and bw >= max_kg:
            continue
        return row

    return None


def _province_surcharge_match(
    cfg: QuoteSurchargeConfigContext,
    dest: Dest,
) -> bool:
    row_prov_code = _s(cfg.province_code)
    row_prov_name = _s(cfg.province_name)
    dest_prov_code = _s(getattr(dest, "province_code", None))
    dest_prov_name = _s(getattr(dest, "province", None))

    if row_prov_code and dest_prov_code:
        return row_prov_code == dest_prov_code
    if row_prov_name and dest_prov_name:
        return row_prov_name == dest_prov_name
    return False


def _city_match(
    row: QuoteSurchargeCityContext,
    dest: Dest,
) -> bool:
    row_city_code = _s(row.city_code)
    row_city_name = _s(row.city_name)
    dest_city_code = _s(getattr(dest, "city_code", None))
    dest_city_name = _s(getattr(dest, "city", None))

    if row_city_code and dest_city_code:
        return row_city_code == dest_city_code
    if row_city_name and dest_city_name:
        return row_city_name == dest_city_name
    return False


def _select_surcharge_from_configs(
    *,
    configs: List[QuoteSurchargeConfigContext],
    dest: Dest,
    reasons: List[str],
) -> tuple[
    QuoteSurchargeConfigContext | None,
    QuoteSurchargeCityContext | None,
    float,
    JsonObject | None,
]:
    matched_configs = [
        cfg
        for cfg in configs
        if bool(cfg.active) and _province_surcharge_match(cfg, dest)
    ]
    if not matched_configs:
        return None, None, 0.0, None

    cfg = sorted(matched_configs, key=lambda x: int(x.id))[0]
    province_mode = str(cfg.province_mode or "province").strip().lower()

    if province_mode == "province":
        amt = float(cfg.fixed_amount or 0.0)
        reasons.append(
            f"surcharge_select: province>{cfg.province_name or cfg.province_code or cfg.id}"
        )
        return cfg, None, amt, {"kind": "fixed", "amount": amt}

    city_rows = [
        row
        for row in (cfg.cities or [])
        if bool(row.active) and _city_match(row, dest)
    ]
    if not city_rows:
        return cfg, None, 0.0, None

    city_row = sorted(city_rows, key=lambda x: int(x.id))[0]
    amt = float(city_row.fixed_amount or 0.0)
    reasons.append(
        "surcharge_select: city>"
        f"{cfg.province_name or cfg.province_code}-"
        f"{city_row.city_name or city_row.city_code}"
    )
    return cfg, city_row, amt, {"kind": "fixed", "amount": amt}


def calc_quote_level3(
    *,
    ctx: QuoteCalcContext,
    dest: Dest,
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    flags: Optional[List[str]],
) -> JsonObject:
    _ = flags

    billable_weight_rule = _context_billable_weight_rule(ctx)
    weight_info = _compute_billable_weight_kg(
        real_weight_kg,
        dims_cm,
        billable_weight_rule,
    )
    bw = float(weight_info["billable_weight_kg"])

    template_rounding = _context_rounding_rule(ctx)
    weight_info["rounding"] = template_rounding
    weight_info["rounding_source"] = "quote.context.defaults"

    group, hit_member = _match_destination_group(ctx.groups, dest)
    if not group:
        raise ValueError("no matching destination group")

    group_matrix = [
        r
        for r in ctx.matrix_rows
        if int(r.group_id) == int(group.id) and bool(r.active)
    ]

    row = _match_pricing_matrix(group_matrix, bw)
    if not row:
        raise ValueError("no matching pricing matrix")

    reasons: List[str] = []
    if hit_member is not None:
        reasons.append(
            "group_match: "
            f"group={group.name} "
            f"member(province={hit_member.province_name or hit_member.province_code})"
        )
    else:
        reasons.append(f"group_match: group={group.name} (fallback)")

    mn = float(row.min_kg)
    mx = None if row.max_kg is None else float(row.max_kg)
    reasons.append(
        f"matrix_match: [{mn}kg, {('inf' if mx is None else mx)}kg) (billable={bw}kg)"
    )

    base_amt, base_detail = _calc_base_amount(row, bw, template_rounding)

    group_out: JsonObject = {
        "id": int(group.id),
        "name": group.name,
        "hit_member": _to_hit_member_out_level3(hit_member),
        "source": "level3",
    }
    matrix_out: JsonObject = {
        "id": int(row.id),
        "module_range_id": int(row.module_range_id),
        "min_kg": float(row.min_kg),
        "max_kg": None if row.max_kg is None else float(row.max_kg),
        "pricing_mode": str(row.pricing_mode),
        "flat_amount": None if row.flat_amount is None else float(row.flat_amount),
        "base_amount": None if row.base_amount is None else float(row.base_amount),
        "rate_per_kg": None if row.rate_per_kg is None else float(row.rate_per_kg),
        "base_kg": None if row.base_kg is None else float(row.base_kg),
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
            ctx=ctx,
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
        configs=ctx.surcharge_configs,
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
                    f"{chosen_cfg.province_name or chosen_cfg.province_code}-"
                    f"{chosen_city.city_name or chosen_city.city_code}"
                    if chosen_city is not None
                    else str(
                        chosen_cfg.province_name
                        or chosen_cfg.province_code
                        or chosen_cfg.id
                    )
                ),
                "scope": "city" if chosen_city is not None else "province",
                "province_code": chosen_cfg.province_code,
                "city_code": chosen_city.city_code if chosen_city is not None else None,
                "province_name": chosen_cfg.province_name,
                "city_name": chosen_city.city_name if chosen_city is not None else None,
                "amount": float(surcharge_amt),
                "detail": surcharge_detail,
            }
        )
        reasons.append(f"surcharge_hit: +{float(surcharge_amt):.2f}")

    extra_sum = float(surcharge_sum)
    total = float(base_amt) + float(extra_sum)
    reasons.append(f"total={total:.2f} {ctx.currency}")

    breakdown = {
        "base": {
            "amount": float(base_amt),
            **(base_detail if isinstance(base_detail, dict) else {}),
        },
        "surcharges": s_details,
        "summary": {
            "base_amount": float(base_amt),
            "surcharge_amount": float(surcharge_sum),
            "extra_amount": float(extra_sum),
            "total_amount": float(total),
        },
    }

    return _build_level3_quote_result(
        ctx=ctx,
        quote_status="OK",
        reasons=reasons,
        dest=dest,
        weight_info=weight_info,
        group_out=group_out,
        matrix_out=matrix_out,
        breakdown=breakdown,
        total_amount=total,
    )
