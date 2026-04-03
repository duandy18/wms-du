from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.models.shipping_provider_pricing_template_destination_group import (
    ShippingProviderPricingTemplateDestinationGroup,
)
from app.models.shipping_provider_pricing_template_destination_group_member import (
    ShippingProviderPricingTemplateDestinationGroupMember,
)
from app.tms.permissions import check_config_perm

from app.tms.pricing.templates.module_resources_shared import (
    delete_group_matrix_rows,
    ensure_template_draft,
    generate_group_display_name,
    list_group_members,
    list_template_groups,
    load_group_or_404,
    load_template_or_404,
    replace_group_members,
    validate_group_provinces_unique_in_template,
)
from app.tms.pricing.templates.contracts.module_groups import (
    ModuleGroupDeleteOut,
    ModuleGroupOut,
    ModuleGroupProvinceOut,
    ModuleGroupsOut,
    ModuleGroupSingleOut,
    ModuleGroupWriteIn,
)


router = APIRouter()


def _build_group_out(
    *,
    group: ShippingProviderPricingTemplateDestinationGroup,
    members: List[ShippingProviderPricingTemplateDestinationGroupMember],
) -> ModuleGroupOut:
    return ModuleGroupOut(
        id=int(group.id),
        template_id=int(group.template_id),
        name=str(group.name),
        sort_order=int(group.sort_order),
        active=bool(group.active),
        provinces=[
            ModuleGroupProvinceOut(
                id=int(m.id),
                group_id=int(m.group_id),
                province_code=m.province_code,
                province_name=m.province_name,
            )
            for m in members
        ],
    )


@router.get(
    "/templates/{template_id}/groups",
    response_model=ModuleGroupsOut,
    name="pricing_template_groups_get",
)
def get_template_groups(
    template_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.read"])

    template = load_template_or_404(db, template_id)
    groups = list_template_groups(db, template_id=int(template.id))
    group_ids = [int(g.id) for g in groups]

    members_by_group: Dict[int, List[ShippingProviderPricingTemplateDestinationGroupMember]] = {}
    if group_ids:
        members_by_group = list_group_members(db, group_ids=group_ids)

    return ModuleGroupsOut(
        ok=True,
        groups=[
            _build_group_out(
                group=g,
                members=members_by_group.get(int(g.id), []),
            )
            for g in groups
        ],
    )


@router.post(
    "/templates/{template_id}/groups",
    response_model=ModuleGroupSingleOut,
    name="pricing_template_groups_create",
)
def create_group(
    template_id: int = Path(..., ge=1),
    payload: ModuleGroupWriteIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])

    template = load_template_or_404(db, template_id)
    ensure_template_draft(template)

    provinces = [(p.province_code, p.province_name) for p in payload.provinces]

    validate_group_provinces_unique_in_template(
        db,
        template_id=int(template.id),
        provinces=provinces,
    )

    grp = ShippingProviderPricingTemplateDestinationGroup(
        template_id=int(template.id),
        name="__tmp__",
        sort_order=int(payload.sort_order if payload.sort_order is not None else 0),
        active=bool(payload.active),
    )

    db.add(grp)
    db.flush()

    grp.name = generate_group_display_name(int(grp.id))

    replace_group_members(
        db,
        group_id=int(grp.id),
        provinces=provinces,
    )

    db.commit()

    members_by_group = list_group_members(db, group_ids=[int(grp.id)])

    return ModuleGroupSingleOut(
        ok=True,
        group=_build_group_out(
            group=grp,
            members=members_by_group.get(int(grp.id), []),
        ),
    )


@router.put(
    "/templates/{template_id}/groups/{group_id}",
    response_model=ModuleGroupSingleOut,
    name="pricing_template_groups_update",
)
def update_group(
    template_id: int = Path(..., ge=1),
    group_id: int = Path(..., ge=1),
    payload: ModuleGroupWriteIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])

    template = load_template_or_404(db, template_id)
    ensure_template_draft(template)

    grp = load_group_or_404(db, template_id=int(template.id), group_id=int(group_id))

    provinces = [(p.province_code, p.province_name) for p in payload.provinces]

    validate_group_provinces_unique_in_template(
        db,
        template_id=int(template.id),
        provinces=provinces,
        exclude_group_id=int(grp.id),
    )

    if payload.sort_order is not None:
        grp.sort_order = int(payload.sort_order)
    grp.active = bool(payload.active)

    replace_group_members(
        db,
        group_id=int(grp.id),
        provinces=provinces,
    )

    delete_group_matrix_rows(
        db,
        group_id=int(grp.id),
    )

    db.commit()

    members_by_group = list_group_members(db, group_ids=[int(grp.id)])

    return ModuleGroupSingleOut(
        ok=True,
        group=_build_group_out(
            group=grp,
            members=members_by_group.get(int(grp.id), []),
        ),
    )


@router.delete(
    "/templates/{template_id}/groups/{group_id}",
    response_model=ModuleGroupDeleteOut,
    name="pricing_template_groups_delete",
)
def delete_group(
    template_id: int = Path(..., ge=1),
    group_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_config_perm(db, user, ["config.store.write"])

    template = load_template_or_404(db, template_id)
    ensure_template_draft(template)

    grp = load_group_or_404(db, template_id=int(template.id), group_id=int(group_id))

    db.delete(grp)
    db.commit()

    return ModuleGroupDeleteOut(
        ok=True,
        deleted_group_id=int(group_id),
    )
