from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.tms.permissions import check_config_perm

from app.tms.pricing.templates.schemas.template import (
    TemplateDetailOut,
    TemplateOut,
    TemplateUpdateIn,
)
from app.tms.pricing.templates.validators import validate_default_pricing_mode


def _norm_nonempty(value: str | None, field_name: str) -> str:
    v = str(value or "").strip()
    if not v:
        raise HTTPException(status_code=422, detail=f"{field_name} must be non-empty")
    return v


def _validate_effective_window(
    effective_from,
    effective_to,
) -> None:
    if effective_from and effective_to and effective_from > effective_to:
        raise HTTPException(
            status_code=422,
            detail="effective_from cannot be greater than effective_to",
        )


def _validate_merged_billable_weight_fields(
    *,
    billable_weight_strategy: str,
    volume_divisor: int | None,
    rounding_mode: str,
    rounding_step_kg: float | None,
) -> None:
    if billable_weight_strategy == "actual_only" and volume_divisor is not None:
        raise HTTPException(
            status_code=422,
            detail="volume_divisor must be empty when billable_weight_strategy=actual_only",
        )

    if billable_weight_strategy == "max_actual_volume" and volume_divisor is None:
        raise HTTPException(
            status_code=422,
            detail="volume_divisor is required when billable_weight_strategy=max_actual_volume",
        )

    if rounding_mode == "none" and rounding_step_kg is not None:
        raise HTTPException(
            status_code=422,
            detail="rounding_step_kg must be empty when rounding_mode=none",
        )

    if rounding_mode == "ceil" and rounding_step_kg is None:
        raise HTTPException(
            status_code=422,
            detail="rounding_step_kg is required when rounding_mode=ceil",
        )


def _to_template_out(template: ShippingProviderPricingTemplate) -> TemplateOut:
    provider_name = ""
    if getattr(template, "shipping_provider", None) is not None:
        provider_name = getattr(template.shipping_provider, "name", "") or ""

    return TemplateOut(
        id=int(template.id),
        shipping_provider_id=int(template.shipping_provider_id),
        shipping_provider_name=provider_name,
        name=template.name,
        status=template.status,
        archived_at=template.archived_at,
        currency=template.currency,
        effective_from=template.effective_from,
        effective_to=template.effective_to,
        default_pricing_mode=template.default_pricing_mode,
        billable_weight_strategy=template.billable_weight_strategy,
        volume_divisor=template.volume_divisor,
        rounding_mode=template.rounding_mode,
        rounding_step_kg=(
            float(template.rounding_step_kg)
            if template.rounding_step_kg is not None
            else None
        ),
        min_billable_weight_kg=(
            float(template.min_billable_weight_kg)
            if template.min_billable_weight_kg is not None
            else None
        ),
        destination_groups=[],
        surcharge_configs=[],
    )


def register_update_routes(router: APIRouter) -> None:
    @router.patch(
        "/templates/{template_id}",
        response_model=TemplateDetailOut,
        name="pricing_template_update",
    )
    def update_template(
        template_id: int = Path(..., ge=1),
        payload: TemplateUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.write"])

        row = db.get(ShippingProviderPricingTemplate, int(template_id))
        if not row:
            raise HTTPException(status_code=404, detail="PricingTemplate not found")

        data = payload.model_dump(exclude_unset=True)

        if "name" in data:
            row.name = _norm_nonempty(data.get("name"), "name")

        if "status" in data:
            row.status = str(data.get("status"))
            if row.status == "archived":
                row.archived_at = datetime.now(timezone.utc)
            else:
                row.archived_at = None

        if "currency" in data:
            row.currency = str(data.get("currency") or "CNY").strip() or "CNY"

        if "effective_from" in data:
            row.effective_from = data.get("effective_from")
        if "effective_to" in data:
            row.effective_to = data.get("effective_to")

        if "default_pricing_mode" in data:
            try:
                row.default_pricing_mode = validate_default_pricing_mode(
                    data.get("default_pricing_mode")
                )
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

        if "billable_weight_strategy" in data:
            row.billable_weight_strategy = str(data.get("billable_weight_strategy"))

        if "volume_divisor" in data:
            row.volume_divisor = data.get("volume_divisor")

        if "rounding_mode" in data:
            row.rounding_mode = str(data.get("rounding_mode"))

        if "rounding_step_kg" in data:
            row.rounding_step_kg = data.get("rounding_step_kg")

        if "min_billable_weight_kg" in data:
            row.min_billable_weight_kg = data.get("min_billable_weight_kg")

        _validate_effective_window(row.effective_from, row.effective_to)

        _validate_merged_billable_weight_fields(
            billable_weight_strategy=str(row.billable_weight_strategy),
            volume_divisor=row.volume_divisor,
            rounding_mode=str(row.rounding_mode),
            rounding_step_kg=(
                float(row.rounding_step_kg)
                if row.rounding_step_kg is not None
                else None
            ),
        )

        db.commit()
        db.refresh(row)

        return TemplateDetailOut(
            ok=True,
            data=_to_template_out(row),
        )
