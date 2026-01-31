# app/api/routers/shipping_provider_pricing_schemes/scheme_read/detail_routes.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes.schemas import SchemeDetailOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db


def register_detail_routes(router: APIRouter) -> None:
    @router.get(
        "/pricing-schemes/{scheme_id}",
        response_model=SchemeDetailOut,
        name="shipping_provider_pricing_schemes_detail",
    )
    def get_scheme_detail(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.read")
        sch, zones, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(ok=True, data=to_scheme_out(sch, zones=zones, surcharges=surcharges))
