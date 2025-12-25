# app/api/routers/shipping_provider_pricing_schemes_routes_brackets_crud.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_schemas import (
    ZoneBracketCreateIn,
    ZoneBracketOut,
    ZoneBracketUpdateIn,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.api.routers.shipping_provider_pricing_schemes_routes_brackets_shared import (
    as_bracket_out,
    normalize_mode,
    validate_payload_for_mode,
    handle_integrity_error,
    validate_bracket_range,
)
from app.db.deps import get_db
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket


def register_brackets_crud_routes(router: APIRouter) -> None:
    @router.post(
        "/zones/{zone_id}/brackets",
        response_model=ZoneBracketOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_zone_bracket(
        zone_id: int = Path(..., ge=1),
        payload: ZoneBracketCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        validate_bracket_range(payload.min_kg, payload.max_kg)

        mode = normalize_mode(payload.pricing_mode)
        validate_payload_for_mode(
            mode, payload.flat_amount, payload.base_amount, payload.rate_per_kg, payload.base_kg
        )

        b = ShippingProviderZoneBracket(
            zone_id=zone_id,
            min_kg=payload.min_kg,
            max_kg=payload.max_kg,
            pricing_mode=mode,
            flat_amount=payload.flat_amount,
            base_amount=payload.base_amount,
            rate_per_kg=payload.rate_per_kg,
            base_kg=payload.base_kg,
            active=bool(payload.active),
        )

        db.add(b)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            handle_integrity_error(e)

        db.refresh(b)
        return as_bracket_out(b)

    @router.patch(
        "/zone-brackets/{bracket_id}",
        response_model=ZoneBracketOut,
    )
    def update_zone_bracket(
        bracket_id: int = Path(..., ge=1),
        payload: ZoneBracketUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        b = db.get(ShippingProviderZoneBracket, bracket_id)
        if not b:
            raise HTTPException(status_code=404, detail="Bracket not found")

        data = payload.dict(exclude_unset=True)

        if "min_kg" in data and data["min_kg"] is not None:
            b.min_kg = data["min_kg"]
        if "max_kg" in data:
            b.max_kg = data["max_kg"]

        validate_bracket_range(b.min_kg, b.max_kg)

        if "pricing_mode" in data and data["pricing_mode"] is not None:
            b.pricing_mode = normalize_mode(data["pricing_mode"])

        if "flat_amount" in data:
            b.flat_amount = data["flat_amount"]
        if "base_amount" in data:
            b.base_amount = data["base_amount"]
        if "rate_per_kg" in data:
            b.rate_per_kg = data["rate_per_kg"]
        if "base_kg" in data:
            b.base_kg = data["base_kg"]
        if "active" in data:
            b.active = bool(data["active"])

        mode = normalize_mode(str(b.pricing_mode))
        validate_payload_for_mode(
            mode, b.flat_amount, b.base_amount, b.rate_per_kg, getattr(b, "base_kg", None)
        )

        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            handle_integrity_error(e)

        db.refresh(b)
        return as_bracket_out(b)

    @router.delete(
        "/zone-brackets/{bracket_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_zone_bracket(
        bracket_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        b = db.get(ShippingProviderZoneBracket, bracket_id)
        if not b:
            raise HTTPException(status_code=404, detail="Bracket not found")

        db.delete(b)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            handle_integrity_error(e)

        return {"ok": True}
