# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_read.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes_schemas import (
    SchemeDetailOut,
    SchemeListOut,
    SchemeOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-providers/{provider_id}/pricing-schemes",
        response_model=SchemeListOut,
    )
    def list_schemes(
        provider_id: int = Path(..., ge=1),
        active: Optional[bool] = Query(None),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        provider = db.get(ShippingProvider, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="ShippingProvider not found")

        q = db.query(ShippingProviderPricingScheme).filter(
            ShippingProviderPricingScheme.shipping_provider_id == provider_id
        )
        if active is not None:
            q = q.filter(ShippingProviderPricingScheme.active.is_(active))

        schemes = q.order_by(
            ShippingProviderPricingScheme.priority.asc(),
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
            priority=100,
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
            name="DEBUG_SCHEME",
            active=True,
            priority=100,
            currency="CNY",
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
                    priority=100,
                    active=True,
                    condition_json={},
                    amount_json={},
                )
            ],
        )

        return SchemeDetailOut(ok=True, data=sch)
