# app/api/routers/shipping_provider_pricing_schemes/scheme_read/matrix_routes.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes.schemas.zone_brackets_matrix import (
    SegmentRangeOut,
    ZoneBracketsMatrixGroupOut,
    ZoneBracketsMatrixOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_pricing_scheme_segment_template_item import (
    ShippingProviderPricingSchemeSegmentTemplateItem,
)


def _is_active_zone(z) -> bool:
    """
    Zone 在 matrix 中的“参与者合同”：
    - 只允许 active=true 的 zone 参与 matrix 输出
    - 归档/释放省份后的 zone 通常会 active=false（并清空成员），必须从 matrix 参与者集合剔除
    """
    v = getattr(z, "active", True)
    return bool(v) is True


def register_matrix_routes(router: APIRouter) -> None:
    @router.get(
        "/pricing-schemes/{scheme_id}/zone-brackets-matrix",
        response_model=ZoneBracketsMatrixOut,
        name="shipping_provider_pricing_schemes_zone_brackets_matrix",
    )
    def get_zone_brackets_matrix(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        sch, zones, _surcharges = load_scheme_entities(db, scheme_id)

        active_zones = [z for z in (zones or []) if _is_active_zone(z)]

        grouped: Dict[int, list] = {}
        unbound: list = []

        for z in active_zones:
            tid = getattr(z, "segment_template_id", None)
            if tid is None:
                unbound.append(z)
                continue
            grouped.setdefault(int(tid), []).append(z)

        template_ids = sorted(grouped.keys())

        templates: Dict[int, ShippingProviderPricingSchemeSegmentTemplate] = {}
        if template_ids:
            rows = (
                db.query(ShippingProviderPricingSchemeSegmentTemplate)
                .filter(ShippingProviderPricingSchemeSegmentTemplate.id.in_(template_ids))
                .order_by(ShippingProviderPricingSchemeSegmentTemplate.id.asc())
                .all()
            )
            templates = {int(t.id): t for t in rows}

        items_by_tpl: Dict[int, List[ShippingProviderPricingSchemeSegmentTemplateItem]] = {}
        if template_ids:
            items = (
                db.query(ShippingProviderPricingSchemeSegmentTemplateItem)
                .filter(ShippingProviderPricingSchemeSegmentTemplateItem.template_id.in_(template_ids))
                .order_by(
                    ShippingProviderPricingSchemeSegmentTemplateItem.template_id.asc(),
                    ShippingProviderPricingSchemeSegmentTemplateItem.ord.asc(),
                    ShippingProviderPricingSchemeSegmentTemplateItem.id.asc(),
                )
                .all()
            )
            for it in items:
                items_by_tpl.setdefault(int(it.template_id), []).append(it)

        groups: List[ZoneBracketsMatrixGroupOut] = []

        for tid in template_ids:
            tpl = templates.get(tid)
            if tpl is None:
                raise HTTPException(
                    status_code=500,
                    detail=f"Zone references missing segment_template_id={tid} (scheme_id={scheme_id})",
                )

            if int(getattr(tpl, "scheme_id", 0)) != int(scheme_id):
                raise HTTPException(
                    status_code=409,
                    detail=f"Segment template does not belong to this scheme (template_id={tid}, scheme_id={scheme_id})",
                )

            segs: List[SegmentRangeOut] = []
            for it in items_by_tpl.get(tid, []):
                if getattr(it, "active", True) is False:
                    continue
                segs.append(
                    SegmentRangeOut(
                        ord=int(getattr(it, "ord", 0)),
                        min_kg=Decimal(str(getattr(it, "min_kg"))),
                        max_kg=(Decimal(str(getattr(it, "max_kg"))) if getattr(it, "max_kg", None) is not None else None),
                        active=bool(getattr(it, "active", True)),
                    )
                )

            groups.append(
                ZoneBracketsMatrixGroupOut(
                    segment_template_id=tid,
                    template_name=str(getattr(tpl, "name", "") or "").strip() or f"template#{tid}",
                    template_status=str(getattr(tpl, "status", "") or "").strip() or "unknown",
                    template_is_active=bool(getattr(tpl, "is_active", False)),
                    segments=segs,
                    zones=grouped.get(tid, []),
                )
            )

        return ZoneBracketsMatrixOut(ok=True, scheme_id=int(getattr(sch, "id", scheme_id)), groups=groups, unbound_zones=unbound)
