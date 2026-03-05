# app/api/routers/pricing_integrity/fix_unbind_archived_templates.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.pricing_integrity_schemas import (
    PricingIntegrityFixUnbindArchivedTemplatesIn,
    PricingIntegrityFixUnbindArchivedTemplatesItemOut,
    PricingIntegrityFixUnbindArchivedTemplatesOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_zone import ShippingProviderZone


def exec_fix_unbind_archived_templates(
    db: Session,
    *,
    scheme_id: int,
    template_ids: list[int],
    dry_run: bool,
) -> PricingIntegrityFixUnbindArchivedTemplatesOut:
    template_ids = list(dict.fromkeys([int(x) for x in template_ids if int(x) > 0]))
    if not template_ids:
        raise HTTPException(status_code=422, detail="template_ids must not be empty")

    templates = (
        db.query(ShippingProviderPricingSchemeSegmentTemplate)
        .filter(ShippingProviderPricingSchemeSegmentTemplate.id.in_(template_ids))
        .order_by(ShippingProviderPricingSchemeSegmentTemplate.id.asc())
        .all()
    )
    tpl_by_id = {t.id: t for t in templates}

    items: list[PricingIntegrityFixUnbindArchivedTemplatesItemOut] = []

    for tid in template_ids:
        t = tpl_by_id.get(tid)
        if t is None:
            items.append(
                PricingIntegrityFixUnbindArchivedTemplatesItemOut(
                    template_id=tid,
                    template_name="",
                    ok=False,
                    error="Template not found",
                )
            )
            continue

        if int(getattr(t, "scheme_id", 0)) != int(scheme_id):
            items.append(
                PricingIntegrityFixUnbindArchivedTemplatesItemOut(
                    template_id=tid,
                    template_name=str(getattr(t, "name", "")),
                    ok=False,
                    template_status=str(getattr(t, "status", "")),
                    error="Template does not belong to this scheme",
                )
            )
            continue

        status_val = str(getattr(t, "status", "") or "")
        if status_val != "archived":
            items.append(
                PricingIntegrityFixUnbindArchivedTemplatesItemOut(
                    template_id=tid,
                    template_name=str(getattr(t, "name", "")),
                    ok=False,
                    template_status=status_val,
                    error="Template is not archived; unbind-archived-templates only supports status=archived",
                )
            )
            continue

        zs = (
            db.query(ShippingProviderZone)
            .filter(
                ShippingProviderZone.scheme_id == scheme_id,
                ShippingProviderZone.segment_template_id == tid,
            )
            .order_by(ShippingProviderZone.id.asc())
            .all()
        )
        zone_ids = [int(z.id) for z in zs]
        zone_names = [str(z.name) for z in zs]

        items.append(
            PricingIntegrityFixUnbindArchivedTemplatesItemOut(
                template_id=tid,
                template_name=str(getattr(t, "name", "")),
                ok=True,
                template_status=status_val,
                would_unbind_zone_ids=zone_ids,
                would_unbind_zone_names=zone_names[:50],
                would_unbind_zone_n=len(zone_ids),
            )
        )

    if dry_run:
        return PricingIntegrityFixUnbindArchivedTemplatesOut(scheme_id=scheme_id, dry_run=True, items=items)

    try:
        for it in items:
            if not it.ok:
                continue
            tid = it.template_id
            db.query(ShippingProviderZone).filter(
                ShippingProviderZone.scheme_id == scheme_id,
                ShippingProviderZone.segment_template_id == tid,
            ).update(
                {ShippingProviderZone.segment_template_id: None},
                synchronize_session=False,
            )
        db.commit()

    except IntegrityError as e:
        db.rollback()
        msg = (str(e.orig) if getattr(e, "orig", None) is not None else str(e)).lower()
        raise HTTPException(status_code=409, detail=f"Conflict while unbind archived templates: {msg}")

    for it in items:
        if not it.ok:
            continue
        remain = (
            db.query(ShippingProviderZone.id)
            .filter(
                ShippingProviderZone.scheme_id == scheme_id,
                ShippingProviderZone.segment_template_id == it.template_id,
            )
            .count()
        )
        it.after_unbound_zone_n = int(remain)

    return PricingIntegrityFixUnbindArchivedTemplatesOut(scheme_id=scheme_id, dry_run=False, items=items)


def register(router: APIRouter) -> None:
    @router.post(
        "/ops/pricing-integrity/fix/unbind-archived-templates",
        response_model=PricingIntegrityFixUnbindArchivedTemplatesOut,
        status_code=status.HTTP_200_OK,
    )
    def ops_fix_unbind_archived_templates(
        payload: PricingIntegrityFixUnbindArchivedTemplatesIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        return exec_fix_unbind_archived_templates(
            db,
            scheme_id=payload.scheme_id,
            template_ids=payload.template_ids,
            dry_run=bool(payload.dry_run),
        )
