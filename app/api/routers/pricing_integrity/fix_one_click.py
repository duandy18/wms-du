# app/api/routers/pricing_integrity/fix_one_click.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.pricing_integrity_schemas import (
    PricingIntegrityFixArchiveReleaseOut,
    PricingIntegrityFixDetachZoneBracketsOut,
    PricingIntegrityFixUnbindArchivedTemplatesOut,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_zone import ShippingProviderZone

from .fix_archive_release import exec_fix_archive_release_provinces
from .fix_detach_brackets import exec_fix_detach_zone_brackets
from .fix_unbind_archived_templates import exec_fix_unbind_archived_templates
from .helpers import count_brackets, count_province_members


def register(router: APIRouter) -> None:
    @router.post(
        "/ops/pricing-integrity/schemes/{scheme_id}/fix/archive-release-all-provinces",
        response_model=PricingIntegrityFixArchiveReleaseOut,
        status_code=status.HTTP_200_OK,
    )
    def ops_fix_archive_release_all_provinces(
        scheme_id: int = Path(..., ge=1),
        dry_run: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        zones_archived = (
            db.query(ShippingProviderZone)
            .filter(
                ShippingProviderZone.scheme_id == scheme_id,
                ShippingProviderZone.active == False,  # noqa: E712
            )
            .order_by(ShippingProviderZone.id.asc())
            .all()
        )
        target_ids: list[int] = []
        for z in zones_archived:
            if count_province_members(db, zone_id=z.id) > 0:
                target_ids.append(int(z.id))

        return exec_fix_archive_release_provinces(db, scheme_id=scheme_id, zone_ids=target_ids, dry_run=bool(dry_run))

    @router.post(
        "/ops/pricing-integrity/schemes/{scheme_id}/fix/detach-brackets-all",
        response_model=PricingIntegrityFixDetachZoneBracketsOut,
        status_code=status.HTTP_200_OK,
    )
    def ops_fix_detach_brackets_all(
        scheme_id: int = Path(..., ge=1),
        dry_run: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        zones_all = (
            db.query(ShippingProviderZone)
            .filter(ShippingProviderZone.scheme_id == scheme_id)
            .order_by(ShippingProviderZone.id.asc())
            .all()
        )
        target_ids: list[int] = []
        for z in zones_all:
            if count_province_members(db, zone_id=z.id) != 0:
                continue
            if count_brackets(db, zone_id=z.id) > 0:
                target_ids.append(int(z.id))

        return exec_fix_detach_zone_brackets(db, scheme_id=scheme_id, zone_ids=target_ids, dry_run=bool(dry_run))

    @router.post(
        "/ops/pricing-integrity/schemes/{scheme_id}/fix/unbind-archived-templates-all",
        response_model=PricingIntegrityFixUnbindArchivedTemplatesOut,
        status_code=status.HTTP_200_OK,
    )
    def ops_fix_unbind_archived_templates_all(
        scheme_id: int = Path(..., ge=1),
        dry_run: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        archived_templates = (
            db.query(ShippingProviderPricingSchemeSegmentTemplate)
            .filter(
                ShippingProviderPricingSchemeSegmentTemplate.scheme_id == scheme_id,
                ShippingProviderPricingSchemeSegmentTemplate.status == "archived",
            )
            .order_by(ShippingProviderPricingSchemeSegmentTemplate.id.asc())
            .all()
        )
        if not archived_templates:
            return PricingIntegrityFixUnbindArchivedTemplatesOut(scheme_id=scheme_id, dry_run=bool(dry_run), items=[])

        tpl_ids = [int(t.id) for t in archived_templates]
        ref_tpl_ids = (
            db.query(ShippingProviderZone.segment_template_id)
            .filter(
                ShippingProviderZone.scheme_id == scheme_id,
                ShippingProviderZone.segment_template_id.in_(tpl_ids),
            )
            .distinct()
            .all()
        )
        target_ids = [int(x[0]) for x in ref_tpl_ids if x and x[0] is not None]

        return exec_fix_unbind_archived_templates(db, scheme_id=scheme_id, template_ids=target_ids, dry_run=bool(dry_run))
