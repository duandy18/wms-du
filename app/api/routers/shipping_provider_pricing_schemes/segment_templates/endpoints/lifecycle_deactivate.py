# app/api/routers/shipping_provider_pricing_schemes/segment_templates/endpoints/lifecycle_deactivate.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routers.shipping_provider_pricing_schemes.schemas.segment_template import SegmentTemplateDetailOut
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate


def register_deactivate_routes(router: APIRouter) -> None:
    @router.post(
        "/segment-templates/{template_id}:deactivate",
        response_model=SegmentTemplateDetailOut,
        tags=["shipping_provider_pricing_schemes"],
    )
    def deactivate_template(
        template_id: int,
        db: Session = Depends(get_db),
    ) -> SegmentTemplateDetailOut:
        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")

        # ✅ 合同：只有 published 才允许进入“可绑定区域”候选池；deactivate 同样要求 published
        # （草稿不可绑定；归档不可绑定）
        if str(tpl.status or "") != "published":
            raise HTTPException(status_code=409, detail="Only published template can be deactivated")

        # 幂等：已是 false 直接返回
        tpl.is_active = False
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        return SegmentTemplateDetailOut(ok=True, data=tpl)
