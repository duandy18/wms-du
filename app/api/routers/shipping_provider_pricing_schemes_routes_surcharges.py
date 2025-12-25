# app/api/routers/shipping_provider_pricing_schemes_routes_surcharges.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_surcharge_out
from app.api.routers.shipping_provider_pricing_schemes_schemas import (
    SurchargeCreateIn,
    SurchargeOut,
    SurchargeUpdateIn,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm, norm_nonempty
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge


def register_surcharges_routes(router: APIRouter) -> None:
    @router.post(
        "/pricing-schemes/{scheme_id}/surcharges",
        response_model=SurchargeOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_surcharge(
        scheme_id: int = Path(..., ge=1),
        payload: SurchargeCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        s = ShippingProviderSurcharge(
            scheme_id=scheme_id,
            name=norm_nonempty(payload.name, "name"),
            priority=int(payload.priority),
            active=bool(payload.active),
            condition_json=payload.condition_json,
            amount_json=payload.amount_json,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return to_surcharge_out(s)

    @router.patch(
        "/surcharges/{surcharge_id}",
        response_model=SurchargeOut,
    )
    def update_surcharge(
        surcharge_id: int = Path(..., ge=1),
        payload: SurchargeUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        s = db.get(ShippingProviderSurcharge, surcharge_id)
        if not s:
            raise HTTPException(status_code=404, detail="Surcharge not found")

        data = payload.dict(exclude_unset=True)

        if "name" in data:
            s.name = norm_nonempty(data.get("name"), "name")
        if "priority" in data:
            s.priority = int(data["priority"])
        if "active" in data:
            s.active = bool(data["active"])
        if "condition_json" in data and data["condition_json"] is not None:
            s.condition_json = data["condition_json"]
        if "amount_json" in data and data["amount_json"] is not None:
            s.amount_json = data["amount_json"]

        db.commit()
        db.refresh(s)
        return to_surcharge_out(s)

    @router.delete(
        "/surcharges/{surcharge_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_surcharge(
        surcharge_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        s = db.get(ShippingProviderSurcharge, surcharge_id)
        if not s:
            raise HTTPException(status_code=404, detail="Surcharge not found")

        db.delete(s)
        db.commit()
        return {"ok": True}
