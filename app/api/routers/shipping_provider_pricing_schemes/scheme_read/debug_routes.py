# app/api/routers/shipping_provider_pricing_schemes/scheme_read/debug_routes.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_schemas import SchemeDetailOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db


def register_debug_routes(router: APIRouter) -> None:
    @router.get(
        "/pricing-schemes/{scheme_id}/__debug_echo",
        response_model=SchemeDetailOut,
        name="shipping_provider_pricing_schemes_debug_echo",
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
