from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.tms.permissions import check_config_perm

from app.tms.pricing.templates.repository import build_template_stats, serialize_template_out
from app.tms.pricing.templates.schemas.template import (
    TemplateCreateIn,
    TemplateDetailOut,
)


def _norm_nonempty(value: str | None, field_name: str) -> str:
    v = str(value or "").strip()
    if not v:
        raise HTTPException(status_code=422, detail=f"{field_name} must be non-empty")
    return v


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

        row = ShippingProviderPricingTemplate(
            shipping_provider_id=int(payload.shipping_provider_id),
            name=_norm_nonempty(payload.name, "name"),
            status="draft",
            archived_at=None,
            validation_status="not_validated",
        )

        db.add(row)
        db.flush()
        db.commit()
        db.refresh(row)

        if getattr(row, "shipping_provider", None) is None:
            row.shipping_provider = provider

        stats = build_template_stats(db, template_id=int(row.id))

        return TemplateDetailOut(
            ok=True,
            data=serialize_template_out(row, include_detail=False, stats=stats),
        )
