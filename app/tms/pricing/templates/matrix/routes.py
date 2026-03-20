from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.shipping_provider_pricing_template_matrix import (
    ShippingProviderPricingTemplateMatrix,
)
from app.tms.permissions import check_config_perm

from app.tms.pricing.templates.module_resources_shared import (
    ensure_template_draft,
    list_template_groups,
    list_template_matrix_cells,
    list_template_ranges,
    load_template_or_404,
)
from app.tms.pricing.templates.schemas.module_matrix_cells import (
    ModuleMatrixCellOut,
    ModuleMatrixCellsOut,
    ModuleMatrixCellsPutIn,
)


router = APIRouter()


@router.get(
    "/templates/{template_id}/matrix-cells",
    response_model=ModuleMatrixCellsOut,
    name="pricing_template_matrix_get",
)
def get_template_matrix_cells(
    template_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.read"])

    template = load_template_or_404(db, template_id)
    rows = list_template_matrix_cells(db, template_id=int(template.id))

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

    return ModuleMatrixCellsOut(ok=True, cells=out)


@router.put(
    "/templates/{template_id}/matrix-cells",
    response_model=ModuleMatrixCellsOut,
    name="pricing_template_matrix_put",
)
def put_template_matrix_cells(
    template_id: int = Path(..., ge=1),
    payload: ModuleMatrixCellsPutIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])

    template = load_template_or_404(db, template_id)
    ensure_template_draft(template)

    groups = list_template_groups(db, template_id=int(template.id))
    ranges = list_template_ranges(db, template_id=int(template.id))

    group_ids = {int(g.id) for g in groups}
    range_ids = {int(r.id) for r in ranges}

    for c in payload.cells:
        if int(c.group_id) not in group_ids:
            raise HTTPException(
                status_code=422,
                detail=f"group_id {c.group_id} does not belong to template",
            )

        if int(c.module_range_id) not in range_ids:
            raise HTTPException(
                status_code=422,
                detail=f"module_range_id {c.module_range_id} does not belong to template",
            )

    db.query(ShippingProviderPricingTemplateMatrix).filter(
        ShippingProviderPricingTemplateMatrix.group_id.in_(group_ids) if group_ids else False
    ).delete(synchronize_session=False)

    db.flush()

    created: List[ShippingProviderPricingTemplateMatrix] = []

    for c in payload.cells:
        row = ShippingProviderPricingTemplateMatrix(
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

    return ModuleMatrixCellsOut(ok=True, cells=out)
