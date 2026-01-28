# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_read.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes_schemas import (
    SchemeDetailOut,
    SchemeListOut,
    SchemeOut,
)
from app.api.routers.shipping_provider_pricing_schemes.schemas.zone_brackets_matrix import (
    ZoneBracketsMatrixOut,
    ZoneBracketsMatrixGroupOut,
    SegmentRangeOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_pricing_scheme_segment_template_item import (
    ShippingProviderPricingSchemeSegmentTemplateItem,
)


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-providers/{provider_id}/pricing-schemes",
        response_model=SchemeListOut,
    )
    def list_schemes(
        provider_id: int = Path(..., ge=1),
        active: Optional[bool] = Query(None),
        include_archived: bool = Query(False),
        include_inactive: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        provider = db.get(ShippingProvider, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="ShippingProvider not found")

        q = (
            db.query(ShippingProviderPricingScheme)
            .options(selectinload(ShippingProviderPricingScheme.shipping_provider))
            .filter(ShippingProviderPricingScheme.shipping_provider_id == provider_id)
        )

        if not include_archived:
            q = q.filter(ShippingProviderPricingScheme.archived_at.is_(None))

        if active is not None:
            q = q.filter(ShippingProviderPricingScheme.active.is_(active))
        else:
            if not include_inactive:
                q = q.filter(ShippingProviderPricingScheme.active.is_(True))

        schemes = q.order_by(
            ShippingProviderPricingScheme.active.desc(),
            ShippingProviderPricingScheme.id.asc(),
        ).all()

        data: List[SchemeOut] = [to_scheme_out(sch, zones=[], surcharges=[]) for sch in schemes]
        return SchemeListOut(ok=True, data=data)

    @router.get(
        "/pricing-schemes/{scheme_id}",
        response_model=SchemeDetailOut,
    )
    def get_scheme_detail(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")
        sch, zones, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(ok=True, data=to_scheme_out(sch, zones=zones, surcharges=surcharges))

    # ✅ 方案 B：按模板分组的 Zone×Brackets 矩阵（供前端拆成多张表）
    @router.get(
        "/pricing-schemes/{scheme_id}/zone-brackets-matrix",
        response_model=ZoneBracketsMatrixOut,
    )
    def get_zone_brackets_matrix(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        # 复用现有 loader：拿到 zones（含 segment_template_id）与 brackets（含 price_json）
        sch, zones, _surcharges = load_scheme_entities(db, scheme_id)

        # 1) 分组：template_id -> zones
        grouped: Dict[int, list] = {}
        unbound: list = []

        for z in zones:
            tid = getattr(z, "segment_template_id", None)
            if tid is None:
                unbound.append(z)
                continue
            grouped.setdefault(int(tid), []).append(z)

        template_ids = sorted(grouped.keys())

        # 2) 批量查 templates（避免 N+1）
        templates: Dict[int, ShippingProviderPricingSchemeSegmentTemplate] = {}
        if template_ids:
            rows = (
                db.query(ShippingProviderPricingSchemeSegmentTemplate)
                .filter(ShippingProviderPricingSchemeSegmentTemplate.id.in_(template_ids))
                .order_by(ShippingProviderPricingSchemeSegmentTemplate.id.asc())
                .all()
            )
            templates = {int(t.id): t for t in rows}

        # 3) 批量查 items（避免 N+1）
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
                # 防御性：zone 上绑了一个不存在的模板 id，这本身就是数据损坏
                raise HTTPException(
                    status_code=500,
                    detail=f"Zone references missing segment_template_id={tid} (scheme_id={scheme_id})",
                )

            # ✅ 确保模板属于该 scheme（事实约束）
            if int(getattr(tpl, "scheme_id", 0)) != int(scheme_id):
                raise HTTPException(
                    status_code=409,
                    detail=f"Segment template does not belong to this scheme (template_id={tid}, scheme_id={scheme_id})",
                )

            # 只输出 active items（用于矩阵列/段结构真相）
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

    # ======================================================================
    # DEBUG: echo a fully-populated response (no DB access)
    # Purpose: detect whether a global response wrapper / JSON encoder is
    # turning nested fields into null / empty lists.
    # Remove after diagnosis.
    # ======================================================================
    @router.get(
        "/pricing-schemes/{scheme_id}/__debug_echo",
        response_model=SchemeDetailOut,
    )
    def debug_scheme_detail_echo(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        from app.api.routers.shipping_provider_pricing_schemes_schemas import (
            SchemeOut as _SchemeOut,
            ZoneOut as _ZoneOut,
            ZoneBracketOut as _ZoneBracketOut,
            ZoneMemberOut as _ZoneMemberOut,
            SurchargeOut as _SurchargeOut,
            WeightSegmentIn as _WeightSegmentIn,
        )

        z = _ZoneOut(
            id=123,
            scheme_id=scheme_id,
            name="DEBUG_ZONE",
            active=True,
            members=[_ZoneMemberOut(id=1, zone_id=123, level="province", value="北京市")],
            brackets=[
                _ZoneBracketOut(
                    id=1,
                    zone_id=123,
                    min_kg=Decimal("0"),
                    max_kg=Decimal("1"),
                    pricing_mode="linear_total",
                    flat_amount=None,
                    base_amount=Decimal("3.00"),
                    rate_per_kg=Decimal("1.20"),
                    base_kg=None,
                    price_json={"kind": "linear_total", "base_amount": 3.0, "rate_per_kg": 1.2},
                    active=True,
                )
            ],
        )

        sch = _SchemeOut(
            id=scheme_id,
            shipping_provider_id=1,
            shipping_provider_name="DEBUG_PROVIDER",
            name="DEBUG_SCHEME",
            active=True,
            currency="CNY",
            archived_at=datetime.now(tz=timezone.utc),
            default_pricing_mode="linear_total",
            billable_weight_rule=None,
            segments_json=[
                _WeightSegmentIn(min="0", max="1"),
                _WeightSegmentIn(min="1", max="2"),
                _WeightSegmentIn(min="2", max=""),
            ],
            segments_updated_at=datetime.now(tz=timezone.utc),
            zones=[z],
            surcharges=[
                _SurchargeOut(
                    id=1,
                    scheme_id=scheme_id,
                    name="S1",
                    active=True,
                    condition_json={},
                    amount_json={},
                )
            ],
        )

        return SchemeDetailOut(ok=True, data=sch)
