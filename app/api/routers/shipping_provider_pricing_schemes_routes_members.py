# app/api/routers/shipping_provider_pricing_schemes_routes_members.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_member_out
from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    ZoneMemberCreateIn,
    ZoneMemberOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import (
    check_perm,
    norm_level,
    norm_nonempty,
)
from app.db.deps import get_db
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def register_members_routes(router: APIRouter) -> None:
    @router.post(
        "/zones/{zone_id}/members",
        response_model=ZoneMemberOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_zone_member(
        zone_id: int = Path(..., ge=1),
        payload: ZoneMemberCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        m = ShippingProviderZoneMember(
            zone_id=zone_id,
            level=norm_level(payload.level),
            value=norm_nonempty(payload.value, "value"),
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        return to_member_out(m)

    @router.delete(
        "/zone-members/{member_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_zone_member(
        member_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        m = db.get(ShippingProviderZoneMember, member_id)
        if not m:
            raise HTTPException(status_code=404, detail="Zone member not found")

        db.delete(m)
        db.commit()
        return {"ok": True}
