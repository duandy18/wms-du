from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session, object_session, selectinload

from app.tms.pricing.templates.models.shipping_provider_pricing_template import ShippingProviderPricingTemplate
from app.tms.pricing.templates.models.shipping_provider_pricing_template_destination_group import (
    ShippingProviderPricingTemplateDestinationGroup,
)
from app.tms.pricing.templates.models.shipping_provider_pricing_template_destination_group_member import (
    ShippingProviderPricingTemplateDestinationGroupMember,
)
from app.tms.pricing.templates.models.shipping_provider_pricing_template_matrix import (
    ShippingProviderPricingTemplateMatrix,
)
from app.tms.pricing.templates.models.shipping_provider_pricing_template_module_range import (
    ShippingProviderPricingTemplateModuleRange,
)
from app.tms.pricing.templates.repository import (
    build_template_capabilities,
    build_template_stats,
)


def load_template_or_404(db: Session, template_id: int) -> ShippingProviderPricingTemplate:
    row = (
        db.query(ShippingProviderPricingTemplate)
        .filter(ShippingProviderPricingTemplate.id == int(template_id))
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="PricingTemplate not found")
    return row


def ensure_template_draft(row: ShippingProviderPricingTemplate) -> None:
    session = object_session(row)
    if session is None:
        raise RuntimeError("template row is detached; cannot evaluate template capabilities")

    stats = build_template_stats(session, template_id=int(row.id))
    caps = build_template_capabilities(template=row, stats=stats)

    if caps.can_edit_structure:
        return

    if caps.readonly_reason == "validated_template":
        raise HTTPException(
            status_code=400,
            detail="Validated template cannot be modified; clone a new draft to edit",
        )

    if caps.readonly_reason == "archived_template":
        raise HTTPException(
            status_code=400,
            detail="Archived template cannot be modified; clone a new draft to edit",
        )

    if caps.readonly_reason == "cloned_template_structure_locked":
        raise HTTPException(
            status_code=400,
            detail="Cloned template cannot modify weight ranges or destination groups; create a new template if you need a different structure",
        )

    raise HTTPException(
        status_code=400,
        detail="Template cannot be modified in current state",
    )


def load_group_or_404(
    db: Session,
    *,
    template_id: int,
    group_id: int,
) -> ShippingProviderPricingTemplateDestinationGroup:
    grp = (
        db.query(ShippingProviderPricingTemplateDestinationGroup)
        .options(
            selectinload(ShippingProviderPricingTemplateDestinationGroup.members),
            selectinload(ShippingProviderPricingTemplateDestinationGroup.matrix_rows),
        )
        .filter(
            ShippingProviderPricingTemplateDestinationGroup.id == int(group_id),
            ShippingProviderPricingTemplateDestinationGroup.template_id == int(template_id),
        )
        .one_or_none()
    )
    if not grp:
        raise HTTPException(status_code=404, detail="Group not found")
    return grp


def load_range_or_404(
    db: Session,
    *,
    template_id: int,
    range_id: int,
) -> ShippingProviderPricingTemplateModuleRange:
    row = (
        db.query(ShippingProviderPricingTemplateModuleRange)
        .filter(
            ShippingProviderPricingTemplateModuleRange.id == int(range_id),
            ShippingProviderPricingTemplateModuleRange.template_id == int(template_id),
        )
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Range not found")
    return row


def list_template_ranges(
    db: Session,
    *,
    template_id: int,
) -> List[ShippingProviderPricingTemplateModuleRange]:
    return (
        db.query(ShippingProviderPricingTemplateModuleRange)
        .filter(ShippingProviderPricingTemplateModuleRange.template_id == int(template_id))
        .order_by(
            ShippingProviderPricingTemplateModuleRange.sort_order.asc(),
            ShippingProviderPricingTemplateModuleRange.id.asc(),
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
        if prev_max is not None and min_kg < prev_max:
            raise HTTPException(status_code=422, detail="weight ranges overlap")
        prev_max = max_kg


def list_template_groups(
    db: Session,
    *,
    template_id: int,
) -> List[ShippingProviderPricingTemplateDestinationGroup]:
    return (
        db.query(ShippingProviderPricingTemplateDestinationGroup)
        .options(selectinload(ShippingProviderPricingTemplateDestinationGroup.members))
        .filter(ShippingProviderPricingTemplateDestinationGroup.template_id == int(template_id))
        .order_by(
            ShippingProviderPricingTemplateDestinationGroup.sort_order.asc(),
            ShippingProviderPricingTemplateDestinationGroup.id.asc(),
        )
        .all()
    )


def list_group_members(
    db: Session,
    *,
    group_ids: List[int],
) -> Dict[int, List[ShippingProviderPricingTemplateDestinationGroupMember]]:
    if not group_ids:
        return {}

    rows = (
        db.query(ShippingProviderPricingTemplateDestinationGroupMember)
        .filter(ShippingProviderPricingTemplateDestinationGroupMember.group_id.in_(group_ids))
        .all()
    )

    result: Dict[int, List[ShippingProviderPricingTemplateDestinationGroupMember]] = {}
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
                raise HTTPException(status_code=422, detail=f"duplicate province inside group: {gname}")

            seen.add(k)

            if k in owner and owner[k] != gname:
                label = name or code or "unknown"
                raise HTTPException(
                    status_code=422,
                    detail=f"province {label} cannot appear in multiple groups",
                )

            owner[k] = gname


def validate_group_provinces_unique_in_template(
    db: Session,
    *,
    template_id: int,
    provinces: List[Tuple[Optional[str], Optional[str]]],
    exclude_group_id: Optional[int] = None,
) -> None:
    groups = list_template_groups(db, template_id=template_id)

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
    db.query(ShippingProviderPricingTemplateDestinationGroupMember).filter(
        ShippingProviderPricingTemplateDestinationGroupMember.group_id == int(group_id)
    ).delete(synchronize_session=False)

    for code, name in provinces:
        db.add(
            ShippingProviderPricingTemplateDestinationGroupMember(
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
    db.query(ShippingProviderPricingTemplateMatrix).filter(
        ShippingProviderPricingTemplateMatrix.group_id == int(group_id)
    ).delete(synchronize_session=False)


def generate_group_display_name(group_id: int) -> str:
    return f"G-{group_id}"


def list_template_matrix_cells(
    db: Session,
    *,
    template_id: int,
) -> List[ShippingProviderPricingTemplateMatrix]:
    groups = list_template_groups(db, template_id=template_id)
    group_ids = [int(g.id) for g in groups]

    if not group_ids:
        return []

    return (
        db.query(ShippingProviderPricingTemplateMatrix)
        .filter(ShippingProviderPricingTemplateMatrix.group_id.in_(group_ids))
        .order_by(
            ShippingProviderPricingTemplateMatrix.group_id.asc(),
            ShippingProviderPricingTemplateMatrix.module_range_id.asc(),
        )
        .all()
    )


def validate_template_ready_for_binding(
    db: Session,
    *,
    template_id: int,
) -> None:
    load_template_or_404(db, template_id)

    ranges = list_template_ranges(db, template_id=template_id)
    groups = list_template_groups(db, template_id=template_id)

    if not ranges:
        raise HTTPException(status_code=422, detail="template has no weight ranges")

    if not groups:
        raise HTTPException(status_code=422, detail="template has no destination groups")

    cells = list_template_matrix_cells(db, template_id=template_id)
    expected = len(ranges) * len(groups)

    if len(cells) != expected:
        raise HTTPException(status_code=422, detail="template pricing matrix incomplete")
