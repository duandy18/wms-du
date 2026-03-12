# app/api/routers/shipping_provider_pricing_schemes/scheme_read/debug_routes.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import SchemeDetailOut
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

        from app.api.routers.shipping_provider_pricing_schemes.schemas import (
            DestinationGroupOut as _DestinationGroupOut,
            DestinationGroupProvinceOut as _DestinationGroupProvinceOut,
            SchemeOut as _SchemeOut,
            SurchargeConfigCityOut as _SurchargeConfigCityOut,
            SurchargeConfigOut as _SurchargeConfigOut,
        )

        g = _DestinationGroupOut(
            id=123,
            scheme_id=scheme_id,
            name="DEBUG_GROUP",
            active=True,
            provinces=[
                _DestinationGroupProvinceOut(
                    id=1,
                    group_id=123,
                    province_code="110000",
                    province_name="北京市",
                )
            ],
        )

        cfg = _SurchargeConfigOut(
            id=1,
            scheme_id=scheme_id,
            province_code="110000",
            province_name="北京市",
            province_mode="cities",
            fixed_amount=Decimal("0"),
            active=True,
            cities=[
                _SurchargeConfigCityOut(
                    id=11,
                    config_id=1,
                    city_code="110100",
                    city_name="北京市",
                    fixed_amount=Decimal("1.00"),
                    active=True,
                )
            ],
        )

        sch = _SchemeOut(
            id=scheme_id,
            shipping_provider_id=1,
            shipping_provider_name="DEBUG_PROVIDER",
            name="DEBUG_SCHEME",
            status="draft",
            archived_at=datetime.now(tz=timezone.utc),
            currency="CNY",
            effective_from=None,
            effective_to=None,
            default_pricing_mode="linear_total",
            billable_weight_strategy="actual_only",
            volume_divisor=None,
            rounding_mode="none",
            rounding_step_kg=None,
            min_billable_weight_kg=None,
            destination_groups=[g],
            surcharge_configs=[cfg],
        )

        return SchemeDetailOut(ok=True, data=sch)
