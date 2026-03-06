# app/api/routers/shipping_provider_pricing_schemes/scheme_read/list_routes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes.schemas import SchemeListOut, SchemeOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def register_list_routes(router: APIRouter) -> None:
    @router.get(
        "/shipping-providers/{provider_id}/pricing-schemes",
        response_model=SchemeListOut,
        name="shipping_provider_pricing_schemes_list",
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

        if include_inactive:
            check_perm(db, user, "config.store.write")

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

        data: List[SchemeOut] = [
            to_scheme_out(sch, destination_groups=[], surcharges=[])
            for sch in schemes
        ]
        return SchemeListOut(ok=True, data=data)

    @router.get(
        "/shipping-providers/{provider_id}/pricing-schemes/active",
        response_model=SchemeListOut,
        name="shipping_provider_pricing_schemes_list_active",
    )
    def list_active_schemes_for_provider(
        provider_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")

        provider = db.get(ShippingProvider, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="ShippingProvider not found")

        schemes = (
            db.query(ShippingProviderPricingScheme)
            .options(selectinload(ShippingProviderPricingScheme.shipping_provider))
            .filter(ShippingProviderPricingScheme.shipping_provider_id == provider_id)
            .filter(ShippingProviderPricingScheme.archived_at.is_(None))
            .filter(ShippingProviderPricingScheme.active.is_(True))
            .order_by(ShippingProviderPricingScheme.id.asc())
            .all()
        )

        data: List[SchemeOut] = [
            to_scheme_out(sch, destination_groups=[], surcharges=[])
            for sch in schemes
        ]
        return SchemeListOut(ok=True, data=data)
