from __future__ import annotations

from decimal import Decimal
from typing import List, Tuple

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.shipping_assist.pricing.templates.models.shipping_provider_pricing_template_module_range import (
    ShippingProviderPricingTemplateModuleRange,
)
from app.shipping_assist.permissions import check_config_perm

from app.shipping_assist.pricing.templates.module_resources_shared import (
    ensure_template_draft,
    list_template_ranges,
    load_template_or_404,
    validate_ranges_no_overlap,
)
from app.shipping_assist.pricing.templates.contracts.module_ranges import (
    ModuleRangeOut,
    ModuleRangesOut,
    ModuleRangesPutIn,
)


router = APIRouter()


def _label(min_kg: Decimal, max_kg: Decimal | None) -> str:
    if max_kg is None:
        return f"{min_kg}kg+"
    return f"{min_kg}-{max_kg}kg"


@router.get(
    "/templates/{template_id}/ranges",
    response_model=ModuleRangesOut,
    name="pricing_template_ranges_get",
)
def get_template_ranges(
    template_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.read"])

    template = load_template_or_404(db, template_id)
    rows = list_template_ranges(db, template_id=int(template.id))

    out: List[ModuleRangeOut] = []
    for r in rows:
        out.append(
            ModuleRangeOut(
                id=int(r.id),
                template_id=int(r.template_id),
                min_kg=r.min_kg,
                max_kg=r.max_kg,
                sort_order=int(r.sort_order),
                default_pricing_mode=str(r.default_pricing_mode),
                label=_label(r.min_kg, r.max_kg),
            )
        )

    return ModuleRangesOut(ok=True, ranges=out)


@router.put(
    "/templates/{template_id}/ranges",
    response_model=ModuleRangesOut,
    name="pricing_template_ranges_put",
)
def put_template_ranges(
    template_id: int = Path(..., ge=1),
    payload: ModuleRangesPutIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])

    template = load_template_or_404(db, template_id)
    ensure_template_draft(template)

    ranges = payload.ranges
    pairs: List[Tuple[Decimal, Decimal | None]] = [(r.min_kg, r.max_kg) for r in ranges]
    validate_ranges_no_overlap(pairs)

    db.query(ShippingProviderPricingTemplateModuleRange).filter(
        ShippingProviderPricingTemplateModuleRange.template_id == int(template.id)
    ).delete(synchronize_session=False)

    db.flush()

    created: List[ShippingProviderPricingTemplateModuleRange] = []

    for idx, r in enumerate(ranges):
        row = ShippingProviderPricingTemplateModuleRange(
            template_id=int(template.id),
            min_kg=r.min_kg,
            max_kg=r.max_kg,
            sort_order=int(r.sort_order if r.sort_order is not None else idx),
            default_pricing_mode=str(r.default_pricing_mode),
        )
        db.add(row)
        db.flush()
        created.append(row)

    db.commit()

    out: List[ModuleRangeOut] = []
    for r in created:
        out.append(
            ModuleRangeOut(
                id=int(r.id),
                template_id=int(r.template_id),
                min_kg=r.min_kg,
                max_kg=r.max_kg,
                sort_order=int(r.sort_order),
                default_pricing_mode=str(r.default_pricing_mode),
                label=_label(r.min_kg, r.max_kg),
            )
        )

    return ModuleRangesOut(ok=True, ranges=out)
