# app/api/routers/shipping_provider_pricing_schemes_routes_pricing_matrix_replace.py
from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    PricingMatrixOut,
    PricingMatrixReplaceIn,
    PricingMatrixReplaceOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.api.routers.shipping_provider_pricing_schemes_routes_pricing_matrix_shared import (
    as_pricing_matrix_out,
    handle_integrity_error,
    normalize_mode,
    validate_complete_active_matrix,
    validate_payload_for_mode,
    validate_pricing_matrix_range,
)
from app.db.deps import get_db
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix


@dataclass
class _MatrixDraftRow:
    min_kg: object
    max_kg: object
    pricing_mode: str
    flat_amount: object
    base_amount: object
    rate_per_kg: object
    base_kg: object
    active: bool


def register_pricing_matrix_replace_routes(router: APIRouter) -> None:
    @router.put(
        "/destination-groups/{group_id}/pricing-matrix",
        response_model=PricingMatrixReplaceOut,
        status_code=status.HTTP_200_OK,
    )
    def replace_pricing_matrix(
        group_id: int = Path(..., ge=1),
        payload: PricingMatrixReplaceIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        group = db.get(ShippingProviderDestinationGroup, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Destination group not found")

        drafts: list[_MatrixDraftRow] = []
        for item in payload.rows:
            validate_pricing_matrix_range(item.min_kg, item.max_kg)
            mode = normalize_mode(item.pricing_mode)
            validate_payload_for_mode(
                mode,
                item.flat_amount,
                item.base_amount,
                item.rate_per_kg,
                item.base_kg,
            )
            drafts.append(
                _MatrixDraftRow(
                    min_kg=item.min_kg,
                    max_kg=item.max_kg,
                    pricing_mode=mode,
                    flat_amount=item.flat_amount,
                    base_amount=item.base_amount,
                    rate_per_kg=item.rate_per_kg,
                    base_kg=item.base_kg,
                    active=bool(item.active),
                )
            )

        validate_complete_active_matrix(drafts)

        db.query(ShippingProviderPricingMatrix).filter(
            ShippingProviderPricingMatrix.group_id == group_id
        ).delete(synchronize_session=False)

        created_rows: list[ShippingProviderPricingMatrix] = []
        for d in drafts:
            row = ShippingProviderPricingMatrix(
                group_id=group_id,
                min_kg=d.min_kg,
                max_kg=d.max_kg,
                pricing_mode=d.pricing_mode,
                flat_amount=d.flat_amount,
                base_amount=d.base_amount,
                rate_per_kg=d.rate_per_kg,
                base_kg=d.base_kg,
                active=d.active,
            )
            db.add(row)
            created_rows.append(row)

        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            handle_integrity_error(e)

        out_rows: list[PricingMatrixOut] = []
        for row in created_rows:
            db.refresh(row)
            out_rows.append(as_pricing_matrix_out(row))

        out_rows.sort(
            key=lambda r: (
                r.min_kg,
                r.max_kg if r.max_kg is not None else r.min_kg + 999999,
                r.id,
            )
        )

        return PricingMatrixReplaceOut(
            ok=True,
            group_id=group_id,
            replaced_count=len(out_rows),
            rows=out_rows,
        )
