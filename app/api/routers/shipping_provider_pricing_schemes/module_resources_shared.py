# app/api/routers/shipping_provider_pricing_schemes/module_resources_shared.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_module import ShippingProviderPricingSchemeModule
from app.models.shipping_provider_pricing_scheme_module_range import (
    ShippingProviderPricingSchemeModuleRange,
)
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix


# ---------------------------------------------------------
# 基础加载
# ---------------------------------------------------------

def load_scheme_or_404(db: Session, scheme_id: int) -> ShippingProviderPricingScheme:
    sch = (
        db.query(ShippingProviderPricingScheme)
        .filter(ShippingProviderPricingScheme.id == int(scheme_id))
        .one_or_none()
    )
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return sch


def ensure_scheme_draft(sch: ShippingProviderPricingScheme) -> None:
    if str(sch.status) != "draft":
        raise HTTPException(status_code=400, detail="Only draft scheme can be modified")


def load_module_or_404(
    db: Session,
    *,
    scheme_id: int,
    module_code: str,
) -> ShippingProviderPricingSchemeModule:
    mod = (
        db.query(ShippingProviderPricingSchemeModule)
        .filter(
            ShippingProviderPricingSchemeModule.scheme_id == int(scheme_id),
            ShippingProviderPricingSchemeModule.module_code == str(module_code),
        )
        .one_or_none()
    )
    if not mod:
        raise HTTPException(status_code=404, detail=f"Module not found: {module_code}")
    return mod


# ---------------------------------------------------------
# ranges
# ---------------------------------------------------------

def list_module_ranges(
    db: Session,
    *,
    module_id: int,
) -> List[ShippingProviderPricingSchemeModuleRange]:
    return (
        db.query(ShippingProviderPricingSchemeModuleRange)
        .filter(ShippingProviderPricingSchemeModuleRange.module_id == int(module_id))
        .order_by(
            ShippingProviderPricingSchemeModuleRange.sort_order.asc(),
            ShippingProviderPricingSchemeModuleRange.id.asc(),
        )
        .all()
    )


def validate_ranges_no_overlap(
    ranges: Iterable[Tuple[Decimal, Optional[Decimal]]],
) -> None:
    ordered = sorted(
        list(ranges),
        key=lambda x: (x[0], Decimal("999999999") if x[1] is None else x[1]),
    )

    prev_max: Optional[Decimal] = None

    for min_kg, max_kg in ordered:
        if prev_max is not None:
            if prev_max is None:
                raise HTTPException(
                    status_code=422,
                    detail="weight ranges overlap: previous range is open-ended",
                )
            if min_kg < prev_max:
                raise HTTPException(
                    status_code=422,
                    detail="weight ranges overlap",
                )
        prev_max = max_kg


# ---------------------------------------------------------
# groups
# ---------------------------------------------------------

def list_module_groups(
    db: Session,
    *,
    module_id: int,
) -> List[ShippingProviderDestinationGroup]:
    return (
        db.query(ShippingProviderDestinationGroup)
        .filter(ShippingProviderDestinationGroup.module_id == int(module_id))
        .order_by(
            ShippingProviderDestinationGroup.sort_order.asc(),
            ShippingProviderDestinationGroup.id.asc(),
        )
        .all()
    )


def list_group_members(
    db: Session,
    *,
    group_ids: List[int],
) -> Dict[int, List[ShippingProviderDestinationGroupMember]]:
    rows = (
        db.query(ShippingProviderDestinationGroupMember)
        .filter(ShippingProviderDestinationGroupMember.group_id.in_(group_ids))
        .all()
    )

    result: Dict[int, List[ShippingProviderDestinationGroupMember]] = {}

    for r in rows:
        result.setdefault(int(r.group_id), []).append(r)

    return result


def _province_key(code: Optional[str], name: Optional[str]) -> Tuple[str, str]:
    return (str(code or ""), str(name or ""))


def validate_groups_no_duplicate_province(
    groups: Iterable[Tuple[str, List[Tuple[Optional[str], Optional[str]]]]]
) -> None:
    """
    groups:
        [
            (group_name, [(province_code, province_name), ...])
        ]
    """

    owner: Dict[Tuple[str, str], str] = {}

    for gname, provinces in groups:
        seen = set()

        for code, name in provinces:
            k = _province_key(code, name)

            if k in seen:
                raise HTTPException(
                    status_code=422,
                    detail=f"duplicate province inside group: {gname}",
                )

            seen.add(k)

            if k in owner and owner[k] != gname:
                label = name or code or "unknown"
                raise HTTPException(
                    status_code=422,
                    detail=f"province {label} cannot appear in multiple groups",
                )

            owner[k] = gname


# ---------------------------------------------------------
# matrix cells
# ---------------------------------------------------------

def list_module_matrix_cells(
    db: Session,
    *,
    module_id: int,
) -> List[ShippingProviderPricingMatrix]:

    groups = list_module_groups(db, module_id=module_id)
    group_ids = [int(g.id) for g in groups]

    if not group_ids:
        return []

    return (
        db.query(ShippingProviderPricingMatrix)
        .filter(ShippingProviderPricingMatrix.group_id.in_(group_ids))
        .order_by(
            ShippingProviderPricingMatrix.group_id.asc(),
            ShippingProviderPricingMatrix.module_range_id.asc(),
        )
        .all()
    )


# ---------------------------------------------------------
# publish validation
# ---------------------------------------------------------

def validate_scheme_publishable(
    db: Session,
    *,
    scheme_id: int,
) -> None:

    load_scheme_or_404(db, scheme_id)

    modules = (
        db.query(ShippingProviderPricingSchemeModule)
        .filter(ShippingProviderPricingSchemeModule.scheme_id == int(scheme_id))
        .all()
    )

    if not modules:
        raise HTTPException(status_code=422, detail="scheme has no modules")

    for mod in modules:

        ranges = list_module_ranges(db, module_id=int(mod.id))
        groups = list_module_groups(db, module_id=int(mod.id))

        if not ranges:
            raise HTTPException(
                status_code=422,
                detail=f"module {mod.module_code} has no weight ranges",
            )

        if not groups:
            raise HTTPException(
                status_code=422,
                detail=f"module {mod.module_code} has no destination groups",
            )

        cells = list_module_matrix_cells(db, module_id=int(mod.id))

        expected = len(ranges) * len(groups)

        if len(cells) != expected:
            raise HTTPException(
                status_code=422,
                detail=f"module {mod.module_code} pricing matrix incomplete",
            )
