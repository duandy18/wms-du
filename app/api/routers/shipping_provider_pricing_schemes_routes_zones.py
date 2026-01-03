# app/api/routers/shipping_provider_pricing_schemes_routes_zones.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_zone_out
from app.api.routers.shipping_provider_pricing_schemes_schemas import (
    ZoneCreateAtomicIn,
    ZoneCreateIn,
    ZoneOut,
    ZoneUpdateIn,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import (
    check_perm,
    clean_list_str,
    norm_nonempty,
)
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember


def register_zones_routes(router: APIRouter) -> None:
    @router.post(
        "/pricing-schemes/{scheme_id}/zones",
        response_model=ZoneOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_zone(
        scheme_id: int = Path(..., ge=1),
        payload: ZoneCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        z = ShippingProviderZone(
            scheme_id=scheme_id,
            name=norm_nonempty(payload.name, "name"),
            active=bool(payload.active),
        )
        db.add(z)
        db.commit()
        db.refresh(z)
        return to_zone_out(z, [], [])

    @router.post(
        "/pricing-schemes/{scheme_id}/zones-atomic",
        response_model=ZoneOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_zone_atomic(
        scheme_id: int = Path(..., ge=1),
        payload: ZoneCreateAtomicIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        provinces = clean_list_str(payload.provinces)
        if not provinces:
            raise HTTPException(status_code=422, detail="provinces is required (>=1)")

        z = ShippingProviderZone(
            scheme_id=scheme_id,
            name=norm_nonempty(payload.name, "name"),
            active=bool(payload.active),
        )

        try:
            db.add(z)
            db.flush()

            members = [ShippingProviderZoneMember(zone_id=z.id, level="province", value=p) for p in provinces]
            db.add_all(members)

            db.commit()
            db.refresh(z)
        except IntegrityError as e:
            db.rollback()
            msg = (str(e.orig) if getattr(e, "orig", None) is not None else str(e)).lower()

            if "uq_sp_zones_scheme_name" in msg:
                raise HTTPException(status_code=409, detail="Zone name already exists in this scheme")
            if "uq_sp_zone_members_zone_level_value" in msg:
                raise HTTPException(status_code=409, detail="Zone members conflict (duplicate level/value)")
            raise HTTPException(status_code=409, detail="Conflict while creating zone and members")

        members_db = (
            db.query(ShippingProviderZoneMember)
            .filter(ShippingProviderZoneMember.zone_id == z.id)
            .order_by(
                ShippingProviderZoneMember.level.asc(),
                ShippingProviderZoneMember.value.asc(),
                ShippingProviderZoneMember.id.asc(),
            )
            .all()
        )
        return to_zone_out(z, members_db, [])

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

    @router.delete(
        "/zones/{zone_id}",
        status_code=status.HTTP_200_OK,
    )
    def delete_zone(
        zone_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        z = db.get(ShippingProviderZone, zone_id)
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")

        db.delete(z)
        db.commit()
        return {"ok": True}
