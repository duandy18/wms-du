# app/api/routers/shipping_provider_pricing_schemes_routes_module_groups.py
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas.module_groups import (
    ModuleGroupOut,
    ModuleGroupProvinceOut,
    ModuleGroupsOut,
    ModuleGroupsPutIn,
)
from app.api.routers.shipping_provider_pricing_schemes.module_resources_shared import (
    load_scheme_or_404,
    ensure_scheme_draft,
    load_module_or_404,
    list_module_groups,
    list_group_members,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)


def register_module_groups_routes(router: APIRouter) -> None:

    @router.get(
        "/pricing-schemes/{scheme_id}/modules/{module_code}/groups",
        response_model=ModuleGroupsOut,
    )
    def get_module_groups(
        scheme_id: int = Path(..., ge=1),
        module_code: str = Path(...),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        mod = load_module_or_404(db, scheme_id=sch.id, module_code=module_code)

        groups = list_module_groups(db, module_id=int(mod.id))

        group_ids = [int(g.id) for g in groups]

        members: Dict[int, List[ShippingProviderDestinationGroupMember]] = {}
        if group_ids:
            members = list_group_members(db, group_ids=group_ids)

        out: List[ModuleGroupOut] = []

        for g in groups:

            provinces = [
                ModuleGroupProvinceOut(
                    id=int(m.id),
                    group_id=int(m.group_id),
                    province_code=m.province_code,
                    province_name=m.province_name,
                )
                for m in members.get(int(g.id), [])
            ]

            out.append(
                ModuleGroupOut(
                    id=int(g.id),
                    scheme_id=int(g.scheme_id),
                    module_id=int(g.module_id),
                    module_code=str(mod.module_code),
                    name=str(g.name),
                    sort_order=int(g.sort_order),
                    active=bool(g.active),
                    provinces=provinces,
                )
            )

        return ModuleGroupsOut(
            ok=True,
            module_code=str(mod.module_code),
            groups=out,
        )

    @router.put(
        "/pricing-schemes/{scheme_id}/modules/{module_code}/groups",
        response_model=ModuleGroupsOut,
    )
    def put_module_groups(
        scheme_id: int = Path(..., ge=1),
        module_code: str = Path(...),
        payload: ModuleGroupsPutIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = load_scheme_or_404(db, scheme_id)
        ensure_scheme_draft(sch)

        mod = load_module_or_404(db, scheme_id=sch.id, module_code=module_code)

        # 删除旧 groups（cascade 删除 members 和 matrix cells）
        db.query(ShippingProviderDestinationGroup).filter(
            ShippingProviderDestinationGroup.module_id == int(mod.id)
        ).delete(synchronize_session=False)

        db.flush()

        created_groups: List[ShippingProviderDestinationGroup] = []

        for idx, g in enumerate(payload.groups):

            grp = ShippingProviderDestinationGroup(
                scheme_id=int(sch.id),
                module_id=int(mod.id),
                name=str(g.name),
                sort_order=int(g.sort_order if g.sort_order is not None else idx),
                active=bool(g.active),
            )

            db.add(grp)
            db.flush()

            for p in g.provinces:

                db.add(
                    ShippingProviderDestinationGroupMember(
                        group_id=int(grp.id),
                        province_code=p.province_code,
                        province_name=p.province_name,
                    )
                )

            created_groups.append(grp)

        db.commit()

        # 重新读取
        groups = list_module_groups(db, module_id=int(mod.id))
        group_ids = [int(g.id) for g in groups]
        members = list_group_members(db, group_ids=group_ids)

        out: List[ModuleGroupOut] = []

        for g in groups:

            provinces = [
                ModuleGroupProvinceOut(
                    id=int(m.id),
                    group_id=int(m.group_id),
                    province_code=m.province_code,
                    province_name=m.province_name,
                )
                for m in members.get(int(g.id), [])
            ]

            out.append(
                ModuleGroupOut(
                    id=int(g.id),
                    scheme_id=int(g.scheme_id),
                    module_id=int(g.module_id),
                    module_code=str(mod.module_code),
                    name=str(g.name),
                    sort_order=int(g.sort_order),
                    active=bool(g.active),
                    provinces=provinces,
                )
            )

        return ModuleGroupsOut(
            ok=True,
            module_code=str(mod.module_code),
            groups=out,
        )
