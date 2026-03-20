from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.tms.permissions import check_config_perm

from app.tms.pricing.templates.schemas.template import (
    TemplateCreateIn,
    TemplateDetailOut,
    TemplateOut,
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


def _validate_billable_weight_fields(payload: TemplateCreateIn) -> None:
    if payload.billable_weight_strategy == "actual_only" and payload.volume_divisor is not None:
        raise HTTPException(
            status_code=422,
            detail="volume_divisor must be empty when billable_weight_strategy=actual_only",
        )

    if payload.billable_weight_strategy == "max_actual_volume" and payload.volume_divisor is None:
        raise HTTPException(
            status_code=422,
            detail="volume_divisor is required when billable_weight_strategy=max_actual_volume",
        )

    if payload.rounding_mode == "none" and payload.rounding_step_kg is not None:
        raise HTTPException(
            status_code=422,
            detail="rounding_step_kg must be empty when rounding_mode=none",
        )

    if payload.rounding_mode == "ceil" and payload.rounding_step_kg is None:
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


def register_create_routes(router: APIRouter) -> None:
    @router.post(
        "/templates",
        response_model=TemplateDetailOut,
        status_code=status.HTTP_201_CREATED,
        name="pricing_template_create",
    )
    def create_template(
        payload: TemplateCreateIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.write"])

        provider = db.get(ShippingProvider, int(payload.shipping_provider_id))
        if not provider:
            raise HTTPException(status_code=404, detail="ShippingProvider not found")

        _validate_effective_window(payload.effective_from, payload.effective_to)

        try:
            dpm = validate_default_pricing_mode(payload.default_pricing_mode)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        _validate_billable_weight_fields(payload)

        row = ShippingProviderPricingTemplate(
            shipping_provider_id=int(payload.shipping_provider_id),
            name=_norm_nonempty(payload.name, "name"),
            status="draft",
            archived_at=None,
            currency=(payload.currency or "CNY").strip() or "CNY",
            default_pricing_mode=dpm,
            billable_weight_strategy=payload.billable_weight_strategy,
            volume_divisor=payload.volume_divisor,
            rounding_mode=payload.rounding_mode,
            rounding_step_kg=payload.rounding_step_kg,
            min_billable_weight_kg=payload.min_billable_weight_kg,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
        )

        db.add(row)
        db.flush()
        db.commit()
        db.refresh(row)

        if getattr(row, "shipping_provider", None) is None:
            row.shipping_provider = provider

        return TemplateDetailOut(
            ok=True,
            data=_to_template_out(row),
        )
