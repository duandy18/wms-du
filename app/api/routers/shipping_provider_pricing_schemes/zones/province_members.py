# app/api/routers/shipping_provider_pricing_schemes/zones/province_members.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_zone_out
from app.api.routers.shipping_provider_pricing_schemes.schemas import ZoneOut, ZoneProvinceMembersReplaceIn
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm, clean_list_str
from app.api.routers.shipping_provider_pricing_schemes_zones_helpers import assert_provinces_no_overlap
from app.db.deps import get_db
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def register_province_members_routes(router: APIRouter) -> None:
    # ✅ 原子替换某个 Zone 的 province members（用于“编辑省份”）
    @router.put(
        "/zones/{zone_id}/province-members",
        response_model=ZoneOut,
    )
    def replace_zone_province_members(
        zone_id: int = Path(..., ge=1),
        payload: ZoneProvinceMembersReplaceIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        provinces = clean_list_str(payload.provinces)
        if not provinces:
            raise HTTPException(status_code=422, detail="provinces is required (>=1)")

        # ✅ 省份不交叉（排除自己）
        assert_provinces_no_overlap(db, scheme_id=z.scheme_id, provinces=provinces, exclude_zone_id=zone_id)

        try:
            db.query(ShippingProviderZoneMember).filter(
                ShippingProviderZoneMember.zone_id == zone_id,
                ShippingProviderZoneMember.level == "province",
            ).delete(synchronize_session=False)

            db.add_all([ShippingProviderZoneMember(zone_id=zone_id, level="province", value=p) for p in provinces])

            db.commit()
            db.refresh(z)
        except IntegrityError as e:
            db.rollback()
            msg = (str(e.orig) if getattr(e, "orig", None) is not None else str(e)).lower()
            if "uq_sp_zone_members_zone_level_value" in msg:
                raise HTTPException(status_code=409, detail="Zone members conflict (duplicate level/value)")
            raise HTTPException(status_code=409, detail="Conflict while replacing zone province members")

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
