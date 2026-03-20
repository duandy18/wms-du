from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.tms.permissions import check_config_perm

from app.tms.pricing.templates.schemas.template import (
    TemplateListOut,
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


def _build_template_list(db: Session, query):
    templates = query.order_by(
        ShippingProviderPricingTemplate.id.desc(),
    ).all()
    return [_to_template_out(row) for row in templates]


def register_list_routes(router: APIRouter) -> None:
    @router.get(
        "/templates",
        response_model=TemplateListOut,
        name="pricing_templates_list",
    )
    def list_templates(
        shipping_provider_id: int | None = Query(default=None, ge=1),
        status: str | None = Query(default=None),
        include_archived: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.read"])

        q = db.query(ShippingProviderPricingTemplate)

        if shipping_provider_id is not None:
            q = q.filter(
                ShippingProviderPricingTemplate.shipping_provider_id == shipping_provider_id
            )

        if status is not None:
            q = q.filter(ShippingProviderPricingTemplate.status == status)

        if not include_archived:
            q = q.filter(ShippingProviderPricingTemplate.archived_at.is_(None))

        result = _build_template_list(db, q)

        return TemplateListOut(
            ok=True,
            data=result,
        )

    @router.get(
        "/shipping-providers/{provider_id}/templates",
        response_model=TemplateListOut,
        name="pricing_templates_provider_list",
    )
    def list_provider_templates(
        provider_id: int = Path(..., ge=1),
        status: str | None = Query(default=None),
        include_archived: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.read"])

        q = db.query(ShippingProviderPricingTemplate).filter(
            ShippingProviderPricingTemplate.shipping_provider_id == provider_id
        )

        if status is not None:
            q = q.filter(ShippingProviderPricingTemplate.status == status)

        if not include_archived:
            q = q.filter(ShippingProviderPricingTemplate.archived_at.is_(None))

        result = _build_template_list(db, q)

        return TemplateListOut(
            ok=True,
            data=result,
        )
