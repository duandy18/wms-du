# app/api/routers/shipping_provider_pricing_schemes/zones/update.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_zone_out
from app.api.routers.shipping_provider_pricing_schemes.schemas import ZoneOut, ZoneUpdateIn
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm, norm_nonempty
from app.api.routers.shipping_provider_pricing_schemes_zones_helpers import (
    assert_zone_brackets_compatible_with_template,
    load_template_or_422,
)
from app.db.deps import get_db
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def _assert_template_bindable(tpl_status: str | None) -> None:
    # ✅ Zone 绑定只允许：published 且未归档
    if tpl_status == "archived":
        raise HTTPException(status_code=409, detail="cannot bind archived segment template")
    if tpl_status != "published":
        raise HTTPException(status_code=409, detail="cannot bind non-published segment template (must be published)")


def register_update_routes(router: APIRouter) -> None:
    @router.patch(
        "/zones/{zone_id}",
        response_model=ZoneOut,
    )
    def update_zone(
        zone_id: int = Path(..., ge=1),
        payload: ZoneUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        data = payload.dict(exclude_unset=True)

        if "name" in data:
            z.name = norm_nonempty(data.get("name"), "name")
        if "active" in data:
            z.active = bool(data["active"])

        # ✅ 新合同：允许 segment_template_id 为空（解绑），绑定由二维工作台完成
        if "segment_template_id" in data:
            next_tpl_id = data.get("segment_template_id", None)

            if next_tpl_id is None:
                # 防止出现“有 brackets 但没模板”的脏状态：要求先清空 brackets
                has_any_brackets = (
                    db.query(ShippingProviderZoneBracket.id)
                    .filter(ShippingProviderZoneBracket.zone_id == zone_id)
                    .limit(1)
                    .first()
                    is not None
                )
                if has_any_brackets:
                    raise HTTPException(
                        status_code=409,
                        detail="cannot unbind segment_template_id when zone has brackets; clear brackets first",
                    )
                z.segment_template_id = None
            else:
                # 1) 模板必须属于同 scheme（并返回 tpl）
                tpl = load_template_or_422(db, scheme_id=z.scheme_id, template_id=int(next_tpl_id))
                # 2) 绑定只允许 published 且未归档
                _assert_template_bindable(getattr(tpl, "status", None))
                # 3) 若该 zone 已有 brackets，必须兼容
                assert_zone_brackets_compatible_with_template(db, zone_id=zone_id, template_id=int(next_tpl_id))
                z.segment_template_id = int(next_tpl_id)

        db.commit()
        db.refresh(z)

        members = (
            db.query(ShippingProviderZoneMember)
            .filter(ShippingProviderZoneMember.zone_id == zone_id)
            .order_by(
                ShippingProviderZoneMember.level.asc(),
                ShippingProviderZoneMember.value.asc(),
                ShippingProviderZoneMember.id.asc(),
            )
            .all()
        )
        brackets = (
            db.query(ShippingProviderZoneBracket)
            .filter(ShippingProviderZoneBracket.zone_id == zone_id)
            .order_by(
                ShippingProviderZoneBracket.min_kg.asc(),
                ShippingProviderZoneBracket.max_kg.asc().nulls_last(),
                ShippingProviderZoneBracket.id.asc(),
            )
            .all()
        )
        return to_zone_out(z, members, brackets)
