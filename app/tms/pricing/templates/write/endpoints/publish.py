from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.tms.permissions import check_config_perm
from app.tms.pricing.templates.module_resources_shared import validate_template_publishable
from app.tms.pricing.templates.schemas.template import (
    TemplateDetailOut,
    TemplateOut,
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


def register_publish_routes(router: APIRouter) -> None:
    @router.post(
        "/templates/{template_id}/publish",
        response_model=TemplateDetailOut,
        name="pricing_template_publish",
    )
    def publish_template(
        template_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.write"])

        row = db.get(ShippingProviderPricingTemplate, int(template_id))
        if not row:
            raise HTTPException(status_code=404, detail="PricingTemplate not found")

        if str(row.status) != "draft":
            raise HTTPException(status_code=400, detail="Only draft template can be published")

        validate_template_publishable(db, template_id=int(template_id))

        row.status = "active"
        row.archived_at = None

        db.commit()
        db.refresh(row)

        return TemplateDetailOut(
            ok=True,
            data=_to_template_out(row),
        )
