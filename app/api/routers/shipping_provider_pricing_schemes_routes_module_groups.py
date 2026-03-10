# app/api/routers/shipping_provider_pricing_schemes_routes_module_groups.py
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.module_groups import (
    ModuleGroupDeleteOut,
    ModuleGroupOut,
    ModuleGroupProvinceOut,
    ModuleGroupsOut,
    ModuleGroupSingleOut,
    ModuleGroupWriteIn,
)
from app.api.routers.shipping_provider_pricing_schemes.module_resources_shared import (
    delete_group_matrix_rows,
    ensure_scheme_draft,
    generate_group_display_name,
    list_group_members,
    list_scheme_groups,
    load_group_or_404,
    load_scheme_or_404,
    replace_group_members,
    validate_group_provinces_unique_in_scheme,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)


def _build_group_out(
    *,
    group: ShippingProviderDestinationGroup,
    members: List[ShippingProviderDestinationGroupMember],
) -> ModuleGroupOut:
    return ModuleGroupOut(
        id=int(group.id),
        scheme_id=int(group.scheme_id),
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


def register_module_groups_routes(router: APIRouter) -> None:
    @router.get(
        "/pricing-schemes/{scheme_id}/groups",
        response_model=ModuleGroupsOut,
    )
    def get_scheme_groups(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        groups = list_scheme_groups(db, scheme_id=int(sch.id))
        group_ids = [int(g.id) for g in groups]

        members_by_group: Dict[int, List[ShippingProviderDestinationGroupMember]] = {}
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
        "/pricing-schemes/{scheme_id}/groups",
        response_model=ModuleGroupSingleOut,
    )
    def create_group(
        scheme_id: int = Path(..., ge=1),
        payload: ModuleGroupWriteIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        ensure_scheme_draft(sch)

        provinces = [(p.province_code, p.province_name) for p in payload.provinces]

        validate_group_provinces_unique_in_scheme(
            db,
            scheme_id=int(sch.id),
            provinces=provinces,
        )

        grp = ShippingProviderDestinationGroup(
            scheme_id=int(sch.id),
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
        "/pricing-schemes/{scheme_id}/groups/{group_id}",
        response_model=ModuleGroupSingleOut,
    )
    def update_group(
        scheme_id: int = Path(..., ge=1),
        group_id: int = Path(..., ge=1),
        payload: ModuleGroupWriteIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        ensure_scheme_draft(sch)

        grp = load_group_or_404(db, scheme_id=int(sch.id), group_id=int(group_id))

        provinces = [(p.province_code, p.province_name) for p in payload.provinces]

        validate_group_provinces_unique_in_scheme(
            db,
            scheme_id=int(sch.id),
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
        "/pricing-schemes/{scheme_id}/groups/{group_id}",
        response_model=ModuleGroupDeleteOut,
    )
    def delete_group(
        scheme_id: int = Path(..., ge=1),
        group_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        ensure_scheme_draft(sch)

        grp = load_group_or_404(db, scheme_id=int(sch.id), group_id=int(group_id))

        db.delete(grp)
        db.commit()

        return ModuleGroupDeleteOut(
            ok=True,
            deleted_group_id=int(group_id),
        )
