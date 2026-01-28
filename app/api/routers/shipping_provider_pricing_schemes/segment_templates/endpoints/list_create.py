# app/api/routers/shipping_provider_pricing_schemes/segment_templates/routes/list_create.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.segment_template import (
    SegmentTemplateCreateIn,
    SegmentTemplateDetailOut,
    SegmentTemplateListOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate

from ..helpers import now_utc


def register_list_create_routes(router: APIRouter) -> None:
    @router.get(
        "/pricing-schemes/{scheme_id}/segment-templates",
        response_model=SegmentTemplateListOut,
    )
    def list_templates(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        tpls = (
            db.query(ShippingProviderPricingSchemeSegmentTemplate)
            .filter(ShippingProviderPricingSchemeSegmentTemplate.scheme_id == scheme_id)
            .order_by(
                ShippingProviderPricingSchemeSegmentTemplate.is_active.desc(),
                ShippingProviderPricingSchemeSegmentTemplate.id.desc(),
            )
            .all()
        )
        return SegmentTemplateListOut(ok=True, data=tpls)

    @router.post(
        "/pricing-schemes/{scheme_id}/segment-templates",
        response_model=SegmentTemplateDetailOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_template(
        scheme_id: int = Path(..., ge=1),
        payload: SegmentTemplateCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        name = (payload.name or "").strip()
        if not name:
            name = now_utc().strftime("%Y-%m-%d") + " 表头模板"

        tpl = ShippingProviderPricingSchemeSegmentTemplate(
            scheme_id=scheme_id,
            name=name,
            status="draft",
            is_active=False,
            effective_from=payload.effective_from,
            published_at=None,
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)
        return SegmentTemplateDetailOut(ok=True, data=tpl)
