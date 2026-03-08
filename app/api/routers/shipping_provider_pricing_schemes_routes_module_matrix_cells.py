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
    load_scheme_or_404,
    ensure_scheme_draft,
    load_module_or_404,
    list_module_groups,
    list_module_ranges,
    list_module_matrix_cells,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix


def register_module_matrix_cells_routes(router: APIRouter) -> None:

    @router.get(
        "/pricing-schemes/{scheme_id}/modules/{module_code}/matrix-cells",
        response_model=ModuleMatrixCellsOut,
    )
    def get_module_matrix_cells(
        scheme_id: int = Path(..., ge=1),
        module_code: str = Path(...),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        mod = load_module_or_404(db, scheme_id=sch.id, module_code=module_code)

        rows = list_module_matrix_cells(db, module_id=int(mod.id))

        out: List[ModuleMatrixCellOut] = []

        for r in rows:
            out.append(
                ModuleMatrixCellOut(
                    id=int(r.id),
                    group_id=int(r.group_id),
                    module_range_id=int(r.module_range_id),
                    range_module_id=int(r.range_module_id),
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
            module_code=str(mod.module_code),
            cells=out,
        )

    @router.put(
        "/pricing-schemes/{scheme_id}/modules/{module_code}/matrix-cells",
        response_model=ModuleMatrixCellsOut,
    )
    def put_module_matrix_cells(
        scheme_id: int = Path(..., ge=1),
        module_code: str = Path(...),
        payload: ModuleMatrixCellsPutIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        ensure_scheme_draft(sch)

        mod = load_module_or_404(db, scheme_id=sch.id, module_code=module_code)

        groups = list_module_groups(db, module_id=int(mod.id))
        ranges = list_module_ranges(db, module_id=int(mod.id))

        group_ids = {int(g.id) for g in groups}
        range_ids = {int(r.id) for r in ranges}

        # 校验 cells 引用合法
        for c in payload.cells:

            if int(c.group_id) not in group_ids:
                raise HTTPException(
                    status_code=422,
                    detail=f"group_id {c.group_id} does not belong to module {module_code}",
                )

            if int(c.module_range_id) not in range_ids:
                raise HTTPException(
                    status_code=422,
                    detail=f"module_range_id {c.module_range_id} does not belong to module {module_code}",
                )

        # 删除旧 cells
        db.query(ShippingProviderPricingMatrix).filter(
            ShippingProviderPricingMatrix.range_module_id == int(mod.id)
        ).delete(synchronize_session=False)

        db.flush()

        created: List[ShippingProviderPricingMatrix] = []

        for c in payload.cells:

            row = ShippingProviderPricingMatrix(
                group_id=int(c.group_id),
                module_range_id=int(c.module_range_id),
                range_module_id=int(mod.id),
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
                    range_module_id=int(r.range_module_id),
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
            module_code=str(mod.module_code),
            cells=out,
        )
