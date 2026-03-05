# app/api/routers/pricing_integrity/fix_archive_release.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.pricing_integrity_schemas import (
    PricingIntegrityFixArchiveReleaseIn,
    PricingIntegrityFixArchiveReleaseItemOut,
    PricingIntegrityFixArchiveReleaseOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_member import ShippingProviderZoneMember

from .helpers import count_province_members, list_province_members


def exec_fix_archive_release_provinces(
    db: Session,
    *,
    scheme_id: int,
    zone_ids: list[int],
    dry_run: bool,
) -> PricingIntegrityFixArchiveReleaseOut:
    zone_ids = list(dict.fromkeys([int(x) for x in zone_ids if int(x) > 0]))  # stable de-dup
    if not zone_ids:
        raise HTTPException(status_code=422, detail="zone_ids must not be empty")

    zones = (
        db.query(ShippingProviderZone)
        .filter(ShippingProviderZone.id.in_(zone_ids))
        .order_by(ShippingProviderZone.id.asc())
        .all()
    )
    zones_by_id = {z.id: z for z in zones}

    items: list[PricingIntegrityFixArchiveReleaseItemOut] = []

    for zid in zone_ids:
        z = zones_by_id.get(zid)
        if z is None:
            items.append(
                PricingIntegrityFixArchiveReleaseItemOut(
                    zone_id=zid,
                    zone_name="",
                    ok=False,
                    error="Zone not found",
                )
            )
            continue

        if int(getattr(z, "scheme_id", 0)) != int(scheme_id):
            items.append(
                PricingIntegrityFixArchiveReleaseItemOut(
                    zone_id=zid,
                    zone_name=str(getattr(z, "name", "")),
                    ok=False,
                    error="Zone does not belong to this scheme",
                )
            )
            continue

        provinces = list_province_members(db, zone_id=zid)
        items.append(
            PricingIntegrityFixArchiveReleaseItemOut(
                zone_id=zid,
                zone_name=str(getattr(z, "name", "")),
                ok=True,
                would_release_provinces=provinces,
                would_release_n=len(provinces),
            )
        )

    if dry_run:
        return PricingIntegrityFixArchiveReleaseOut(scheme_id=scheme_id, dry_run=True, items=items)

    try:
        for it in items:
            if not it.ok:
                continue
            zid = it.zone_id

            db.query(ShippingProviderZoneMember).filter(
                ShippingProviderZoneMember.zone_id == zid,
                ShippingProviderZoneMember.level == "province",
            ).delete(synchronize_session=False)

            z = zones_by_id.get(zid)
            if z is not None:
                z.active = False

        db.commit()

    except IntegrityError as e:
        db.rollback()
        msg = (str(e.orig) if getattr(e, "orig", None) is not None else str(e)).lower()
        raise HTTPException(status_code=409, detail=f"Conflict while ops archive-release provinces: {msg}")

    for it in items:
        if not it.ok:
            continue
        z = zones_by_id.get(it.zone_id)
        it.after_active = bool(z.active) if z is not None else None
        it.after_province_member_n = count_province_members(db, zone_id=it.zone_id)

    return PricingIntegrityFixArchiveReleaseOut(scheme_id=scheme_id, dry_run=False, items=items)


def register(router: APIRouter) -> None:
    @router.post(
        "/ops/pricing-integrity/fix/archive-release-provinces",
        response_model=PricingIntegrityFixArchiveReleaseOut,
        status_code=status.HTTP_200_OK,
    )
    def ops_fix_archive_release_provinces(
        payload: PricingIntegrityFixArchiveReleaseIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        return exec_fix_archive_release_provinces(
            db,
            scheme_id=payload.scheme_id,
            zone_ids=payload.zone_ids,
            dry_run=bool(payload.dry_run),
        )
