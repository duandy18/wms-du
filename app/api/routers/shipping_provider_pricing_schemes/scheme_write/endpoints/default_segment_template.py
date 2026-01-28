from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes_schemas import SchemeDetailOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate

from ..types import SchemeDefaultSegmentTemplateIn


def register_default_segment_template_routes(router: APIRouter) -> None:
    @router.post(
        "/pricing-schemes/{scheme_id}:set-default-segment-template",
        response_model=SchemeDetailOut,
    )
    def set_default_segment_template(
        scheme_id: int = Path(..., ge=1),
        payload: SchemeDefaultSegmentTemplateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        template_id = payload.template_id

        if template_id is None:
            sch.default_segment_template_id = None
            db.commit()
            db.refresh(sch)
            sch2, zones, surcharges = load_scheme_entities(db, scheme_id)
            return SchemeDetailOut(ok=True, data=to_scheme_out(sch2, zones=zones, surcharges=surcharges))

        tpl = db.get(ShippingProviderPricingSchemeSegmentTemplate, int(template_id))
        if not tpl:
            raise HTTPException(status_code=404, detail="Segment template not found")

        if tpl.scheme_id != scheme_id:
            raise HTTPException(status_code=409, detail="Template does not belong to this scheme")

        st = str(getattr(tpl, "status", "") or "")
        if st == "archived":
            raise HTTPException(status_code=409, detail="Archived template cannot be set as default")
        if st != "published":
            raise HTTPException(status_code=409, detail="Only published template can be set as default")

        sch.default_segment_template_id = tpl.id
        db.commit()
        db.refresh(sch)

        sch2, zones, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(ok=True, data=to_scheme_out(sch2, zones=zones, surcharges=surcharges))
