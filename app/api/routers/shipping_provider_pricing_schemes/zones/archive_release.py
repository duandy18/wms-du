# app/api/routers/shipping_provider_pricing_schemes/zones/archive_release.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_zone_out
from app.api.routers.shipping_provider_pricing_schemes_schemas import ZoneOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def register_archive_release_routes(router: APIRouter) -> None:
    # ✅ 归档-释放省份（等价“退出事实世界 + 释放排他资源”）
    # - 行为：清空 province members + 设置 active=false
    # - 目的：归档后不再占用省份，避免新建/改省份时 409 冲突
    @router.post(
        "/zones/{zone_id}/archive-release-provinces",
        response_model=ZoneOut,
        status_code=status.HTTP_200_OK,
    )
    def archive_release_zone_provinces(
        zone_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        try:
            # 1) 释放省份占用：删除 province members
            db.query(ShippingProviderZoneMember).filter(
                ShippingProviderZoneMember.zone_id == zone_id,
                ShippingProviderZoneMember.level == "province",
            ).delete(synchronize_session=False)

            # 2) 标记不可用（归档）
            z.active = False

            db.commit()
            db.refresh(z)
        except IntegrityError as e:
            db.rollback()
            msg = (str(e.orig) if getattr(e, "orig", None) is not None else str(e)).lower()
            raise HTTPException(status_code=409, detail=f"Conflict while archive-release provinces: {msg}")

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
