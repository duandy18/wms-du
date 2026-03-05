# app/api/routers/shipping_provider_pricing_schemes/segment_templates/routes/detail.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.segment_template import SegmentTemplateDetailOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate


def register_detail_routes(router: APIRouter) -> None:
    @router.get(
        "/segment-templates/{template_id}",
        response_model=SegmentTemplateDetailOut,
    )
    def get_template_detail(
        template_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")
        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")
        return SegmentTemplateDetailOut(ok=True, data=tpl)
