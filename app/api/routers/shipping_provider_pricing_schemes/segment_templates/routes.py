# app/api/routers/shipping_provider_pricing_schemes/segment_templates/routes.py
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.segment_template import (
    SegmentTemplateCreateIn,
    SegmentTemplateDetailOut,
    SegmentTemplateItemActivePatchIn,
    SegmentTemplateItemsPutIn,
    SegmentTemplateListOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_segment_template import (
    ShippingProviderPricingSchemeSegmentTemplate,
)
from app.models.shipping_provider_pricing_scheme_segment_template_item import (
    ShippingProviderPricingSchemeSegmentTemplateItem,
)

from .helpers import (
    now_utc,
    sync_scheme_segments_table,
    template_to_scheme_segments_json,
    to_decimal,
    validate_contiguous,
)


def register_segment_templates_routes(router: APIRouter) -> None:
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

        db.query(ShippingProviderPricingSchemeSegmentTemplate).filter(
            ShippingProviderPricingSchemeSegmentTemplate.scheme_id == tpl.scheme_id,
            ShippingProviderPricingSchemeSegmentTemplate.id != tpl.id,
            ShippingProviderPricingSchemeSegmentTemplate.is_active.is_(True),
        ).update({"is_active": False}, synchronize_session=False)

        tpl.is_active = True

        sch = db.get(ShippingProviderPricingScheme, tpl.scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        sch.segments_json = template_to_scheme_segments_json(items)
        sch.segments_updated_at = now_utc()
        sync_scheme_segments_table(db, sch.id, items)

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

        if tpl.is_active:
            sch = db.get(ShippingProviderPricingScheme, tpl.scheme_id)
            if sch:
                sch.segments_json = template_to_scheme_segments_json(tpl.items or [])
                sch.segments_updated_at = now_utc()
                sync_scheme_segments_table(db, sch.id, tpl.items or [])
                db.commit()
                db.refresh(tpl)

        return SegmentTemplateDetailOut(ok=True, data=tpl)
