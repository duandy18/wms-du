# app/api/routers/shipping_provider_pricing_schemes/segment_templates/routes/lifecycle_activate.py
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.segment_template import SegmentTemplateDetailOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate

from ..helpers import validate_contiguous


def register_activate_routes(router: APIRouter) -> None:
    @router.post(
        "/segment-templates/{template_id}:activate",
        response_model=SegmentTemplateDetailOut,
    )
    def activate_template(
        template_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")

        if tpl.status != "published":
            raise HTTPException(status_code=409, detail="Only published template can be activated")

        items = tpl.items or []
        rows = [
            (int(it.ord), Decimal(str(it.min_kg)), None if it.max_kg is None else Decimal(str(it.max_kg)))
            for it in items
        ]
        validate_contiguous(rows)

        # ✅ 允许同 scheme 多条模板同时 active=true（不再互斥清理其它 active）
        tpl.is_active = True

        # ✅ 冻结：不再用 activate 的副作用去覆盖 scheme.segments_json
        # - scheme.segments_json 仅允许通过 scheme_write 的显式入口修改
        # - 段结构的权威真相已升级为 Zone.segment_template_id（避免隐式漂移）

        db.commit()
        db.refresh(tpl)
        return SegmentTemplateDetailOut(ok=True, data=tpl)
