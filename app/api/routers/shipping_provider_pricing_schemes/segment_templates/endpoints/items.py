# app/api/routers/shipping_provider_pricing_schemes/segment_templates/routes/items.py
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.segment_template import (
    SegmentTemplateDetailOut,
    SegmentTemplateItemActivePatchIn,
    SegmentTemplateItemsPutIn,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_pricing_scheme_segment_template_item import ShippingProviderPricingSchemeSegmentTemplateItem

from ..helpers import to_decimal, validate_contiguous


def register_items_routes(router: APIRouter) -> None:
    @router.put(
        "/segment-templates/{template_id}/items",
        response_model=SegmentTemplateDetailOut,
    )
    def put_template_items(
        template_id: int = Path(..., ge=1),
        payload: SegmentTemplateItemsPutIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")

        if tpl.status != "draft":
            raise HTTPException(status_code=409, detail="Only draft template can be edited")

        items_in = payload.items or []

        rows: List[Tuple[int, Decimal, Optional[Decimal]]] = []
        for it in items_in:
            mn = to_decimal(it.min_kg, "min_kg")
            mx = None if it.max_kg is None else to_decimal(it.max_kg, "max_kg")
            rows.append((int(it.ord), mn, mx))

        validate_contiguous(rows)

        db.query(ShippingProviderPricingSchemeSegmentTemplateItem).filter(
            ShippingProviderPricingSchemeSegmentTemplateItem.template_id == template_id
        ).delete(synchronize_session=False)

        for it in items_in:
            db.add(
                ShippingProviderPricingSchemeSegmentTemplateItem(
                    template_id=template_id,
                    ord=int(it.ord),
                    min_kg=to_decimal(it.min_kg, "min_kg"),
                    max_kg=None if it.max_kg is None else to_decimal(it.max_kg, "max_kg"),
                    active=bool(it.active),
                )
            )

        db.commit()
        db.refresh(tpl)
        return SegmentTemplateDetailOut(ok=True, data=tpl)

    @router.patch(
        "/segment-template-items/{item_id}",
        response_model=SegmentTemplateDetailOut,
    )
    def patch_item_active(
        item_id: int = Path(..., ge=1),
        payload: SegmentTemplateItemActivePatchIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        it = db.get(ShippingProviderPricingSchemeSegmentTemplateItem, item_id)
        if not it:
            raise HTTPException(status_code=404, detail="Template item not found")

        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, it.template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")

        it.active = bool(payload.active)
        db.commit()
        db.refresh(tpl)

        # ✅ 冻结：不再因“tpl.is_active”而同步 scheme.segments_json（多 active 下会隐式漂移）
        # - scheme.segments_json 仅允许通过 scheme_write 的显式入口修改
        # - 段结构权威真相：Zone.segment_template_id

        return SegmentTemplateDetailOut(ok=True, data=tpl)
