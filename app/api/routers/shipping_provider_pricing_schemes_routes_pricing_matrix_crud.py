# app/api/routers/shipping_provider_pricing_schemes_routes_pricing_matrix_crud.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    PricingMatrixCreateIn,
    PricingMatrixOut,
    PricingMatrixUpdateIn,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.api.routers.shipping_provider_pricing_schemes_routes_pricing_matrix_shared import (
    as_pricing_matrix_out,
    handle_integrity_error,
    normalize_mode,
    validate_payload_for_mode,
    validate_pricing_matrix_range,
)
from app.db.deps import get_db
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix


def register_pricing_matrix_crud_routes(router: APIRouter) -> None:
    @router.post(
        "/destination-groups/{group_id}/pricing-matrix",
        response_model=PricingMatrixOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_pricing_matrix_row(
        group_id: int = Path(..., ge=1),
        payload: PricingMatrixCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        group = db.get(ShippingProviderDestinationGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Destination group not found")

        validate_pricing_matrix_range(payload.min_kg, payload.max_kg)

        mode = normalize_mode(payload.pricing_mode)
        validate_payload_for_mode(
            mode,
            payload.flat_amount,
            payload.base_amount,
            payload.rate_per_kg,
            payload.base_kg,
        )

        row = ShippingProviderPricingMatrix(
            group_id=group_id,
            min_kg=payload.min_kg,
            max_kg=payload.max_kg,
            pricing_mode=mode,
            flat_amount=payload.flat_amount,
            base_amount=payload.base_amount,
            rate_per_kg=payload.rate_per_kg,
            base_kg=payload.base_kg,
            active=bool(payload.active),
        )

        db.add(row)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            handle_integrity_error(e)

        db.refresh(row)
        return as_pricing_matrix_out(row)

    @router.patch(
        "/pricing-matrix/{row_id}",
        response_model=PricingMatrixOut,
    )
    def update_pricing_matrix_row(
        row_id: int = Path(..., ge=1),
        payload: PricingMatrixUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        row = db.get(ShippingProviderPricingMatrix, row_id)
        if not row:
            raise HTTPException(status_code=404, detail="Pricing matrix row not found")

        group = db.get(ShippingProviderDestinationGroup, row.group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Destination group not found")

        data = payload.dict(exclude_unset=True)

        if "min_kg" in data and data["min_kg"] is not None:
            row.min_kg = data["min_kg"]
        if "max_kg" in data:
            row.max_kg = data["max_kg"]

        validate_pricing_matrix_range(row.min_kg, row.max_kg)

        if "pricing_mode" in data and data["pricing_mode"] is not None:
            row.pricing_mode = normalize_mode(data["pricing_mode"])

        if "flat_amount" in data:
            row.flat_amount = data["flat_amount"]
        if "base_amount" in data:
            row.base_amount = data["base_amount"]
        if "rate_per_kg" in data:
            row.rate_per_kg = data["rate_per_kg"]
        if "base_kg" in data:
            row.base_kg = data["base_kg"]
        if "active" in data:
            row.active = bool(data["active"])

        mode = normalize_mode(str(row.pricing_mode))
        validate_payload_for_mode(
            mode,
            row.flat_amount,
            row.base_amount,
            row.rate_per_kg,
            getattr(row, "base_kg", None),
        )

        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            handle_integrity_error(e)

        db.refresh(row)
        return as_pricing_matrix_out(row)

    @router.delete(
        "/pricing-matrix/{row_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_pricing_matrix_row(
        row_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        row = db.get(ShippingProviderPricingMatrix, row_id)
        if not row:
            raise HTTPException(status_code=404, detail="Pricing matrix row not found")

        db.delete(row)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            handle_integrity_error(e)

        return {"ok": True}
