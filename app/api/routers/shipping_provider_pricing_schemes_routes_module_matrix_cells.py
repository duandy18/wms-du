# app/api/routers/shipping_provider_pricing_schemes_routes_module_matrix_cells.py
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.module_matrix_cells import (
    ModuleMatrixCellOut,
    ModuleMatrixCellsOut,
    ModuleMatrixCellsPutIn,
)
from app.api.routers.shipping_provider_pricing_schemes.module_resources_shared import (
    ensure_scheme_draft,
    list_scheme_groups,
    list_scheme_matrix_cells,
    list_scheme_ranges,
    load_scheme_or_404,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix


def register_module_matrix_cells_routes(router: APIRouter) -> None:
    @router.get(
        "/pricing-schemes/{scheme_id}/matrix-cells",
        response_model=ModuleMatrixCellsOut,
    )
    def get_scheme_matrix_cells(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        rows = list_scheme_matrix_cells(db, scheme_id=int(sch.id))

        out: List[ModuleMatrixCellOut] = []

        for r in rows:
            out.append(
                ModuleMatrixCellOut(
                    id=int(r.id),
                    group_id=int(r.group_id),
                    module_range_id=int(r.module_range_id),
                    pricing_mode=str(r.pricing_mode),
                    flat_amount=r.flat_amount,
                    base_amount=r.base_amount,
                    rate_per_kg=r.rate_per_kg,
                    base_kg=r.base_kg,
                    active=bool(r.active),
                )
            )

        return ModuleMatrixCellsOut(
            ok=True,
            cells=out,
        )

    @router.put(
        "/pricing-schemes/{scheme_id}/matrix-cells",
        response_model=ModuleMatrixCellsOut,
    )
    def put_scheme_matrix_cells(
        scheme_id: int = Path(..., ge=1),
        payload: ModuleMatrixCellsPutIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        ensure_scheme_draft(sch)

        groups = list_scheme_groups(db, scheme_id=int(sch.id))
        ranges = list_scheme_ranges(db, scheme_id=int(sch.id))

        group_ids = {int(g.id) for g in groups}
        range_ids = {int(r.id) for r in ranges}

        for c in payload.cells:
            if int(c.group_id) not in group_ids:
                raise HTTPException(
                    status_code=422,
                    detail=f"group_id {c.group_id} does not belong to scheme",
                )

            if int(c.module_range_id) not in range_ids:
                raise HTTPException(
                    status_code=422,
                    detail=f"module_range_id {c.module_range_id} does not belong to scheme",
                )

        db.query(ShippingProviderPricingMatrix).filter(
            ShippingProviderPricingMatrix.group_id.in_(group_ids) if group_ids else False
        ).delete(synchronize_session=False)

        db.flush()

        created: List[ShippingProviderPricingMatrix] = []

        for c in payload.cells:
            row = ShippingProviderPricingMatrix(
                group_id=int(c.group_id),
                module_range_id=int(c.module_range_id),
                pricing_mode=str(c.pricing_mode),
                flat_amount=c.flat_amount,
                base_amount=c.base_amount,
                rate_per_kg=c.rate_per_kg,
                base_kg=c.base_kg,
                active=bool(c.active),
            )

            db.add(row)
            db.flush()

            created.append(row)

        db.commit()

        out: List[ModuleMatrixCellOut] = []

        for r in created:
            out.append(
                ModuleMatrixCellOut(
                    id=int(r.id),
                    group_id=int(r.group_id),
                    module_range_id=int(r.module_range_id),
                    pricing_mode=str(r.pricing_mode),
                    flat_amount=r.flat_amount,
                    base_amount=r.base_amount,
                    rate_per_kg=r.rate_per_kg,
                    base_kg=r.base_kg,
                    active=bool(r.active),
                )
            )

        return ModuleMatrixCellsOut(
            ok=True,
            cells=out,
        )
