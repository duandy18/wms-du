# app/api/routers/shipping_provider_pricing_schemes_routes_module_ranges.py
from __future__ import annotations

from decimal import Decimal
from typing import List, Tuple

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.module_ranges import (
    ModuleRangeOut,
    ModuleRangesOut,
    ModuleRangesPutIn,
)
from app.api.routers.shipping_provider_pricing_schemes.module_resources_shared import (
    load_scheme_or_404,
    ensure_scheme_draft,
    load_module_or_404,
    list_module_ranges,
    validate_ranges_no_overlap,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_module_range import (
    ShippingProviderPricingSchemeModuleRange,
)


def _label(min_kg: Decimal, max_kg: Decimal | None) -> str:
    if max_kg is None:
        return f"{min_kg}kg+"
    return f"{min_kg}-{max_kg}kg"


def register_module_ranges_routes(router: APIRouter) -> None:

    @router.get(
        "/pricing-schemes/{scheme_id}/modules/{module_code}/ranges",
        response_model=ModuleRangesOut,
    )
    def get_module_ranges(
        scheme_id: int = Path(..., ge=1),
        module_code: str = Path(...),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        mod = load_module_or_404(db, scheme_id=sch.id, module_code=module_code)

        rows = list_module_ranges(db, module_id=int(mod.id))

        out: List[ModuleRangeOut] = []

        for r in rows:
            out.append(
                ModuleRangeOut(
                    id=int(r.id),
                    module_id=int(r.module_id),
                    module_code=str(mod.module_code),
                    min_kg=r.min_kg,
                    max_kg=r.max_kg,
                    sort_order=int(r.sort_order),
                    label=_label(r.min_kg, r.max_kg),
                )
            )

        return ModuleRangesOut(
            ok=True,
            module_code=str(mod.module_code),
            ranges=out,
        )

    @router.put(
        "/pricing-schemes/{scheme_id}/modules/{module_code}/ranges",
        response_model=ModuleRangesOut,
    )
    def put_module_ranges(
        scheme_id: int = Path(..., ge=1),
        module_code: str = Path(...),
        payload: ModuleRangesPutIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        ensure_scheme_draft(sch)

        mod = load_module_or_404(db, scheme_id=sch.id, module_code=module_code)

        ranges = payload.ranges

        pairs: List[Tuple[Decimal, Decimal | None]] = [
            (r.min_kg, r.max_kg) for r in ranges
        ]

        validate_ranges_no_overlap(pairs)

        # 删除旧 ranges（CASCADE 删除 matrix cells）
        db.query(ShippingProviderPricingSchemeModuleRange).filter(
            ShippingProviderPricingSchemeModuleRange.module_id == int(mod.id)
        ).delete(synchronize_session=False)

        db.flush()

        created: List[ShippingProviderPricingSchemeModuleRange] = []

        for idx, r in enumerate(ranges):

            row = ShippingProviderPricingSchemeModuleRange(
                module_id=int(mod.id),
                min_kg=r.min_kg,
                max_kg=r.max_kg,
                sort_order=int(r.sort_order if r.sort_order is not None else idx),
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
                    module_id=int(r.module_id),
                    module_code=str(mod.module_code),
                    min_kg=r.min_kg,
                    max_kg=r.max_kg,
                    sort_order=int(r.sort_order),
                    label=_label(r.min_kg, r.max_kg),
                )
            )

        return ModuleRangesOut(
            ok=True,
            module_code=str(mod.module_code),
            ranges=out,
        )
