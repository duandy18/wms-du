# app/api/routers/pricing_integrity/fix_detach_brackets.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.pricing_integrity_schemas import (
    PricingIntegrityFixDetachZoneBracketsIn,
    PricingIntegrityFixDetachZoneBracketsItemOut,
    PricingIntegrityFixDetachZoneBracketsOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket

from .helpers import brackets_ranges_preview, count_brackets, count_province_members


def exec_fix_detach_zone_brackets(
    db: Session,
    *,
    scheme_id: int,
    zone_ids: list[int],
    dry_run: bool,
) -> PricingIntegrityFixDetachZoneBracketsOut:
    zone_ids = list(dict.fromkeys([int(x) for x in zone_ids if int(x) > 0]))
    if not zone_ids:
        raise HTTPException(status_code=422, detail="zone_ids must not be empty")

    zones = (
        db.query(ShippingProviderZone)
        .filter(ShippingProviderZone.id.in_(zone_ids))
        .order_by(ShippingProviderZone.id.asc())
        .all()
    )
    zones_by_id = {z.id: z for z in zones}

    items: list[PricingIntegrityFixDetachZoneBracketsItemOut] = []

    for zid in zone_ids:
        z = zones_by_id.get(zid)
        if z is None:
            items.append(
                PricingIntegrityFixDetachZoneBracketsItemOut(
                    zone_id=zid,
                    zone_name="",
                    ok=False,
                    error="Zone not found",
                )
            )
            continue

        if int(getattr(z, "scheme_id", 0)) != int(scheme_id):
            items.append(
                PricingIntegrityFixDetachZoneBracketsItemOut(
                    zone_id=zid,
                    zone_name=str(getattr(z, "name", "")),
                    ok=False,
                    error="Zone does not belong to this scheme",
                )
            )
            continue

        prov_n = count_province_members(db, zone_id=zid)
        br_n = count_brackets(db, zone_id=zid)

        # 护栏：只允许对“已释放省份（members=0）”的 zone 做 brackets 清理
        if prov_n != 0:
            items.append(
                PricingIntegrityFixDetachZoneBracketsItemOut(
                    zone_id=zid,
                    zone_name=str(getattr(z, "name", "")),
                    ok=False,
                    province_member_n=prov_n,
                    would_delete_brackets_n=0,
                    error="Zone still has province members; detach brackets is only allowed for released zones (province_member_n=0)",
                )
            )
            continue

        items.append(
            PricingIntegrityFixDetachZoneBracketsItemOut(
                zone_id=zid,
                zone_name=str(getattr(z, "name", "")),
                ok=True,
                province_member_n=prov_n,
                would_delete_brackets_n=br_n,
                would_delete_ranges_preview=brackets_ranges_preview(db, zone_id=zid, limit=8),
            )
        )

    if dry_run:
        return PricingIntegrityFixDetachZoneBracketsOut(scheme_id=scheme_id, dry_run=True, items=items)

    try:
        for it in items:
            if not it.ok:
                continue
            zid = it.zone_id
            db.query(ShippingProviderZoneBracket).filter(ShippingProviderZoneBracket.zone_id == zid).delete(
                synchronize_session=False
            )

        db.commit()

    except IntegrityError as e:
        db.rollback()
        msg = (str(e.orig) if getattr(e, "orig", None) is not None else str(e)).lower()
        raise HTTPException(status_code=409, detail=f"Conflict while detach zone brackets: {msg}")

    for it in items:
        if not it.ok:
            continue
        it.after_brackets_n = count_brackets(db, zone_id=it.zone_id)

    return PricingIntegrityFixDetachZoneBracketsOut(scheme_id=scheme_id, dry_run=False, items=items)


def register(router: APIRouter) -> None:
    @router.post(
        "/ops/pricing-integrity/fix/detach-zone-brackets",
        response_model=PricingIntegrityFixDetachZoneBracketsOut,
        status_code=status.HTTP_200_OK,
    )
    def ops_fix_detach_zone_brackets(
        payload: PricingIntegrityFixDetachZoneBracketsIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        return exec_fix_detach_zone_brackets(
            db,
            scheme_id=payload.scheme_id,
            zone_ids=payload.zone_ids,
            dry_run=bool(payload.dry_run),
        )
