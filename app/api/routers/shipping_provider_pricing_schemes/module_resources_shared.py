# app/api/routers/shipping_provider_pricing_schemes/module_resources_shared.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
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


def load_group_or_404(
    db: Session,
    *,
    scheme_id: int,
    group_id: int,
) -> ShippingProviderDestinationGroup:
    grp = (
        db.query(ShippingProviderDestinationGroup)
        .filter(
            ShippingProviderDestinationGroup.id == int(group_id),
            ShippingProviderDestinationGroup.scheme_id == int(scheme_id),
        )
        .one_or_none()
    )
    if not grp:
        raise HTTPException(status_code=404, detail="Group not found")
    return grp


def load_range_or_404(
    db: Session,
    *,
    scheme_id: int,
    range_id: int,
) -> ShippingProviderPricingSchemeModuleRange:
    row = (
        db.query(ShippingProviderPricingSchemeModuleRange)
        .filter(
            ShippingProviderPricingSchemeModuleRange.id == int(range_id),
            ShippingProviderPricingSchemeModuleRange.scheme_id == int(scheme_id),
        )
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Range not found")
    return row


# ---------------------------------------------------------
# ranges
# ---------------------------------------------------------


def list_scheme_ranges(
    db: Session,
    *,
    scheme_id: int,
) -> List[ShippingProviderPricingSchemeModuleRange]:
    return (
        db.query(ShippingProviderPricingSchemeModuleRange)
        .filter(ShippingProviderPricingSchemeModuleRange.scheme_id == int(scheme_id))
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
            if min_kg < prev_max:
                raise HTTPException(
                    status_code=422,
                    detail="weight ranges overlap",
                )
        prev_max = max_kg


# ---------------------------------------------------------
# groups
# ---------------------------------------------------------


def list_scheme_groups(
    db: Session,
    *,
    scheme_id: int,
) -> List[ShippingProviderDestinationGroup]:
    return (
        db.query(ShippingProviderDestinationGroup)
        .filter(ShippingProviderDestinationGroup.scheme_id == int(scheme_id))
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
    if not group_ids:
        return {}

    rows = (
        db.query(ShippingProviderDestinationGroupMember)
        .filter(ShippingProviderDestinationGroupMember.group_id.in_(group_ids))
        .all()
    )

    result: Dict[int, List[ShippingProviderDestinationGroupMember]] = {}

    for r in rows:
        result.setdefault(int(r.group_id), []).append(r)

    return result


def province_key(code: Optional[str], name: Optional[str]) -> Tuple[str, str]:
    return (str(code or ""), str(name or ""))


def validate_groups_no_duplicate_province(
    groups: Iterable[Tuple[str, List[Tuple[Optional[str], Optional[str]]]]]
) -> None:
    owner: Dict[Tuple[str, str], str] = {}

    for gname, provinces in groups:
        seen = set()

        for code, name in provinces:
            k = province_key(code, name)

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


def validate_group_provinces_unique_in_scheme(
    db: Session,
    *,
    scheme_id: int,
    provinces: List[Tuple[Optional[str], Optional[str]]],
    exclude_group_id: Optional[int] = None,
) -> None:
    groups = list_scheme_groups(db, scheme_id=scheme_id)

    owner: Dict[Tuple[str, str], int] = {}

    for g in groups:
        if exclude_group_id is not None and int(g.id) == int(exclude_group_id):
            continue

        for m in g.members:
            k = province_key(m.province_code, m.province_name)
            owner[k] = int(g.id)

    seen = set()

    for code, name in provinces:
        k = province_key(code, name)

        if k in seen:
            raise HTTPException(status_code=422, detail="duplicate province in group")

        if k in owner:
            raise HTTPException(status_code=422, detail="province already used in another group")

        seen.add(k)


def replace_group_members(
    db: Session,
    *,
    group_id: int,
    provinces: List[Tuple[Optional[str], Optional[str]]],
) -> None:
    db.query(ShippingProviderDestinationGroupMember).filter(
        ShippingProviderDestinationGroupMember.group_id == int(group_id)
    ).delete(synchronize_session=False)

    for code, name in provinces:
        db.add(
            ShippingProviderDestinationGroupMember(
                group_id=int(group_id),
                province_code=code,
                province_name=name,
            )
        )


def delete_group_matrix_rows(
    db: Session,
    *,
    group_id: int,
) -> None:
    db.query(ShippingProviderPricingMatrix).filter(
        ShippingProviderPricingMatrix.group_id == int(group_id)
    ).delete(synchronize_session=False)


def generate_group_display_name(group_id: int) -> str:
    return f"G-{group_id}"


# ---------------------------------------------------------
# matrix cells
# ---------------------------------------------------------


def list_scheme_matrix_cells(
    db: Session,
    *,
    scheme_id: int,
) -> List[ShippingProviderPricingMatrix]:
    groups = list_scheme_groups(db, scheme_id=scheme_id)
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

    ranges = list_scheme_ranges(db, scheme_id=scheme_id)
    groups = list_scheme_groups(db, scheme_id=scheme_id)

    if not ranges:
        raise HTTPException(status_code=422, detail="scheme has no weight ranges")

    if not groups:
        raise HTTPException(status_code=422, detail="scheme has no destination groups")

    cells = list_scheme_matrix_cells(db, scheme_id=scheme_id)

    expected = len(ranges) * len(groups)

    if len(cells) != expected:
        raise HTTPException(status_code=422, detail="scheme pricing matrix incomplete")
