# app/api/routers/shipping_provider_pricing_schemes_routes_pricing_matrix_shared.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.routers.shipping_provider_pricing_schemes.schemas import PricingMatrixOut
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix


def as_pricing_matrix_out(row: ShippingProviderPricingMatrix) -> PricingMatrixOut:
    base_kg = getattr(row, "base_kg", None)
    return PricingMatrixOut(
        id=row.id,
        group_id=row.group_id,
        min_kg=row.min_kg,
        max_kg=row.max_kg,
        pricing_mode=row.pricing_mode,
        flat_amount=row.flat_amount,
        base_amount=row.base_amount,
        rate_per_kg=row.rate_per_kg,
        base_kg=base_kg,
        active=bool(row.active),
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
        if base_amount is not None or rate_per_kg is not None or base_kg is not None:
            raise HTTPException(status_code=422, detail="flat pricing_mode only allows flat_amount")
        return

    if mode == "linear_total":
        if rate_per_kg is None:
            raise HTTPException(status_code=422, detail="linear_total pricing_mode requires rate_per_kg")
        if flat_amount is not None or base_kg is not None:
            raise HTTPException(
                status_code=422,
                detail="linear_total pricing_mode does not allow flat_amount or base_kg",
            )
        return

    if mode == "step_over":
        if base_kg is None:
            raise HTTPException(status_code=422, detail="step_over pricing_mode requires base_kg")
        if base_amount is None:
            raise HTTPException(status_code=422, detail="step_over pricing_mode requires base_amount")
        if rate_per_kg is None:
            raise HTTPException(status_code=422, detail="step_over pricing_mode requires rate_per_kg")
        if flat_amount is not None:
            raise HTTPException(status_code=422, detail="step_over pricing_mode does not allow flat_amount")
        return

    if mode == "manual_quote":
        if any(v is not None for v in (flat_amount, base_amount, rate_per_kg, base_kg)):
            raise HTTPException(status_code=422, detail="manual_quote pricing_mode does not allow pricing fields")
        return

    raise HTTPException(status_code=422, detail="unsupported pricing_mode")


def validate_pricing_matrix_range(min_kg: Decimal, max_kg: Optional[Decimal]) -> None:
    if max_kg is None:
        return
    if max_kg == Decimal("0"):
        raise HTTPException(
            status_code=422,
            detail="max_kg cannot be 0; use null to represent infinity",
        )
    if max_kg <= min_kg:
        raise HTTPException(status_code=422, detail="max_kg must be > min_kg")


def validate_complete_active_matrix(rows: list[object]) -> None:
    active_rows = [r for r in rows if bool(getattr(r, "active", False))]
    if not active_rows:
        raise HTTPException(status_code=422, detail="at least one active pricing_matrix row is required")

    active_rows.sort(
        key=lambda r: (
            Decimal(str(getattr(r, "min_kg"))),
            Decimal(str(getattr(r, "max_kg"))) if getattr(r, "max_kg", None) is not None else Decimal("999999999"),
        )
    )

    first_min = Decimal(str(getattr(active_rows[0], "min_kg")))
    if first_min != Decimal("0"):
        raise HTTPException(status_code=422, detail="active pricing_matrix must start from min_kg=0")

    for i in range(1, len(active_rows)):
        prev_max = getattr(active_rows[i - 1], "max_kg", None)
        curr_min = Decimal(str(getattr(active_rows[i], "min_kg")))
        if prev_max is None:
            raise HTTPException(status_code=422, detail="open-ended pricing_matrix row must be the last active row")
        prev_max_dec = Decimal(str(prev_max))
        if curr_min != prev_max_dec:
            raise HTTPException(
                status_code=422,
                detail="active pricing_matrix rows must be contiguous: next.min_kg must equal previous max_kg",
            )

    last_max = getattr(active_rows[-1], "max_kg", None)
    if last_max is not None:
        raise HTTPException(status_code=422, detail="active pricing_matrix must end with an open-ended row (max_kg=null)")


def handle_integrity_error(e: IntegrityError) -> None:
    msg = ""
    try:
        msg = (str(getattr(e, "orig", "") or "")).lower()
    except Exception:
        msg = str(e).lower()

    if "uq_sppm_group_min_max_coalesced" in msg or "group_min_max_coalesced" in msg:
        raise HTTPException(
            status_code=409,
            detail="Pricing matrix range already exists in this destination group (min_kg/max_kg conflict)",
        )
    if "excl_sppm_active_group_weight_range_no_overlap" in msg or "no_overlap" in msg:
        raise HTTPException(
            status_code=409,
            detail="Active pricing matrix ranges cannot overlap within the same destination group",
        )
    if "ck_sppm_mode_valid" in msg:
        raise HTTPException(status_code=422, detail="Invalid pricing_mode")
    if "ck_sppm_flat_shape" in msg:
        raise HTTPException(status_code=422, detail="flat pricing_mode only allows flat_amount")
    if "ck_sppm_linear_total_shape" in msg:
        raise HTTPException(
            status_code=422,
            detail="linear_total pricing_mode requires rate_per_kg and does not allow flat_amount/base_kg",
        )
    if "ck_sppm_step_over_shape" in msg:
        raise HTTPException(
            status_code=422,
            detail="step_over pricing_mode requires base_kg, base_amount and rate_per_kg, and does not allow flat_amount",
        )
    if "ck_sppm_manual_quote_shape" in msg:
        raise HTTPException(status_code=422, detail="manual_quote pricing_mode does not allow pricing fields")
    if "ck_sppm_range_valid" in msg or "sppm_range_valid" in msg:
        raise HTTPException(
            status_code=422,
            detail="Invalid pricing matrix range: max_kg must be NULL or > min_kg (and cannot be 0)",
        )

    raise HTTPException(status_code=409, detail="Conflict while saving pricing matrix row")


def normalize_conflict_policy(v: str) -> str:
    t = (v or "").strip().lower()
    if t not in ("skip", "overwrite", "abort"):
        raise HTTPException(
            status_code=422,
            detail="conflict_policy must be one of: skip/overwrite/abort",
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
