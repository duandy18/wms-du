# app/api/routers/shipping_provider_pricing_schemes_routes_brackets_shared.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.routers.shipping_provider_pricing_schemes_schemas import ZoneBracketOut
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket


def as_bracket_out(b: ShippingProviderZoneBracket) -> ZoneBracketOut:
    base_kg = getattr(b, "base_kg", None)
    price_json = getattr(b, "price_json", None) or {}
    return ZoneBracketOut(
        id=b.id,
        zone_id=b.zone_id,
        min_kg=b.min_kg,
        max_kg=b.max_kg,
        pricing_mode=b.pricing_mode,
        flat_amount=b.flat_amount,
        base_amount=b.base_amount,
        rate_per_kg=b.rate_per_kg,
        base_kg=base_kg,
        price_json=price_json,
        active=bool(b.active),
    )


def normalize_mode(raw: str) -> str:
    m = (raw or "").strip().lower()
    if m not in ("flat", "linear_total", "step_over", "manual_quote"):
        raise HTTPException(
            status_code=422,
            detail="pricing_mode must be one of: flat, linear_total, step_over, manual_quote",
        )
    return m


def validate_payload_for_mode(mode: str, flat_amount, base_amount, rate_per_kg, base_kg) -> None:
    if mode == "flat":
        if flat_amount is None:
            raise HTTPException(status_code=422, detail="flat pricing_mode requires flat_amount")
        return
    if mode == "linear_total":
        if rate_per_kg is None:
            raise HTTPException(
                status_code=422, detail="linear_total pricing_mode requires rate_per_kg"
            )
        return
    if mode == "step_over":
        if base_kg is None:
            raise HTTPException(status_code=422, detail="step_over pricing_mode requires base_kg")
        if base_amount is None:
            raise HTTPException(
                status_code=422, detail="step_over pricing_mode requires base_amount"
            )
        if rate_per_kg is None:
            raise HTTPException(
                status_code=422, detail="step_over pricing_mode requires rate_per_kg"
            )
        return
    if mode == "manual_quote":
        return
    raise HTTPException(status_code=422, detail="unsupported pricing_mode")


# =========================================================
# ✅ bracket 区间语义（铁律）：
# - max_kg is NULL 代表 infinity（无上限）
# - max_kg=0 永远非法（无上限请传 NULL）
# - max_kg 非 NULL 必须严格大于 min_kg（>，不是 >=）
# =========================================================
def validate_bracket_range(min_kg: Decimal, max_kg: Optional[Decimal]) -> None:
    if max_kg is None:
        return
    if max_kg == Decimal("0"):
        raise HTTPException(
            status_code=422, detail="max_kg cannot be 0; use null to represent infinity"
        )
    if max_kg <= min_kg:
        raise HTTPException(status_code=422, detail="max_kg must be > min_kg")


def handle_integrity_error(e: IntegrityError) -> None:
    msg = ""
    try:
        msg = (str(getattr(e, "orig", "") or "")).lower()
    except Exception:
        msg = str(e).lower()

    if "uq_spzb_zone_min_max_coalesced" in msg or "zone_min_max_coalesced" in msg:
        raise HTTPException(
            status_code=409,
            detail="Bracket range already exists in this zone (min_kg/max_kg conflict)",
        )
    if "ck_spzb_mode_valid" in msg:
        raise HTTPException(status_code=422, detail="Invalid pricing_mode")
    if "ck_spzb_flat_needs_flat_amount" in msg:
        raise HTTPException(status_code=422, detail="flat pricing_mode requires flat_amount")
    if "ck_spzb_linear_needs_rate" in msg:
        raise HTTPException(
            status_code=422, detail="linear_total pricing_mode requires rate_per_kg"
        )
    if "ck_spzb_range_valid" in msg or "spzb_range_valid" in msg:
        raise HTTPException(
            status_code=422,
            detail="Invalid bracket range: max_kg must be NULL or > min_kg (and cannot be 0)",
        )

    raise HTTPException(status_code=409, detail="Conflict while saving bracket")


def normalize_conflict_policy(v: str) -> str:
    t = (v or "").strip().lower()
    if t not in ("skip", "overwrite", "abort"):
        raise HTTPException(
            status_code=422, detail="conflict_policy must be one of: skip/overwrite/abort"
        )
    return t


def normalize_active_policy(v: str) -> str:
    t = (v or "").strip().lower()
    if t not in ("preserve", "force_active", "force_inactive"):
        raise HTTPException(
            status_code=422,
            detail="active_policy must be one of: preserve/force_active/force_inactive",
        )
    return t


def range_key(min_kg: Decimal, max_kg: Optional[Decimal]) -> Tuple[Decimal, Optional[Decimal]]:
    return (min_kg, max_kg)
