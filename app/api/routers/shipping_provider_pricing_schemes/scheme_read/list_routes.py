# app/api/routers/shipping_provider_pricing_schemes/scheme_read/list_routes.py

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import SchemeListOut
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def _build_scheme_list(db: Session, query):
    schemes = query.order_by(
        ShippingProviderPricingScheme.id.desc(),
    ).all()

    result = []

    for sch in schemes:
        sch2, destination_groups, surcharge_configs = load_scheme_entities(db, int(sch.id))
        result.append(
            to_scheme_out(
                sch2,
                destination_groups=destination_groups,
                surcharge_configs=surcharge_configs,
            )
        )

    return result


def register_list_routes(router: APIRouter) -> None:

    @router.get(
        "/pricing-schemes",
        response_model=SchemeListOut,
    )
    def list_schemes(
        include_archived: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        q = db.query(ShippingProviderPricingScheme)

        # 生命周期：draft / active / archived
        if not include_archived:
            q = q.filter(ShippingProviderPricingScheme.archived_at.is_(None))

        result = _build_scheme_list(db, q)

        return SchemeListOut(
            ok=True,
            data=result,
        )

    @router.get(
        "/shipping-providers/{provider_id}/pricing-schemes",
        response_model=SchemeListOut,
    )
    def list_provider_schemes(
        provider_id: int = Path(..., ge=1),
        include_archived: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        q = db.query(ShippingProviderPricingScheme).filter(
            ShippingProviderPricingScheme.shipping_provider_id == provider_id
        )

        if not include_archived:
            q = q.filter(ShippingProviderPricingScheme.archived_at.is_(None))

        result = _build_scheme_list(db, q)

        return SchemeListOut(
            ok=True,
            data=result,
        )
