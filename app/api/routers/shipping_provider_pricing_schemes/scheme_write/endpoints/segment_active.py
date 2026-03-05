from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes.schemas import SchemeDetailOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_segment import ShippingProviderPricingSchemeSegment

from ..types import SchemeSegmentActivePatchIn


def register_segment_active_routes(router: APIRouter) -> None:
    @router.patch(
        "/pricing-schemes/{scheme_id}/segments/{segment_id}",
        response_model=SchemeDetailOut,
    )
    def patch_scheme_segment_active(
        scheme_id: int = Path(..., ge=1),
        segment_id: int = Path(..., ge=1),
        payload: SchemeSegmentActivePatchIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        seg = db.get(ShippingProviderPricingSchemeSegment, segment_id)
        if not seg or seg.scheme_id != scheme_id:
            raise HTTPException(status_code=404, detail="Scheme segment not found")

        seg.active = bool(payload.active)
        db.commit()

        sch2, zones, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(ok=True, data=to_scheme_out(sch2, zones=zones, surcharges=surcharges))
