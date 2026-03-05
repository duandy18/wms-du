# app/api/routers/shipping_provider_pricing_schemes/segment_templates/endpoints/lifecycle_rename.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routers.shipping_provider_pricing_schemes.schemas.segment_template import SegmentTemplateDetailOut
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate


class SegmentTemplateRenameIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80, description="模板名称（用于运营识别）")


def register_rename_routes(router: APIRouter) -> None:
    @router.post(
        "/segment-templates/{template_id}:rename",
        response_model=SegmentTemplateDetailOut,
    )
    def rename_template(
        template_id: int,
        payload: SegmentTemplateRenameIn,
        db: Session = Depends(get_db),
    ) -> SegmentTemplateDetailOut:
        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")

        # ✅ 默认禁止给“已归档”改名：避免把归档对象伪装成活跃维护对象
        if str(tpl.status or "") == "archived":
            raise HTTPException(status_code=409, detail="Archived template cannot be renamed")

        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name is required")

        tpl.name = name
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        return SegmentTemplateDetailOut(ok=True, data=tpl)
