# app/api/routers/shipping_provider_pricing_schemes/segment_templates/routes/lifecycle_publish.py
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.segment_template import SegmentTemplateDetailOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate

from ..helpers import now_utc, validate_contiguous


def register_publish_routes(router: APIRouter) -> None:
    @router.post(
        "/segment-templates/{template_id}:publish",
        response_model=SegmentTemplateDetailOut,
    )
    def publish_template(
        template_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")

        if tpl.status != "draft":
            raise HTTPException(status_code=409, detail="Only draft template can be published")

        items = tpl.items or []
        rows = [
            (int(it.ord), Decimal(str(it.min_kg)), None if it.max_kg is None else Decimal(str(it.max_kg)))
            for it in items
        ]
        validate_contiguous(rows)

        tpl.status = "published"
        tpl.published_at = now_utc()
        db.commit()
        db.refresh(tpl)
        return SegmentTemplateDetailOut(ok=True, data=tpl)
