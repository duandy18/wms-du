# app/api/routers/pricing_integrity/report.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.pricing_integrity_schemas import (
    PricingIntegrityArchivedTemplateStillReferencedIssue,
    PricingIntegrityArchivedZoneIssue,
    PricingIntegrityReleasedZoneStillPricedIssue,
    PricingIntegrityReportOut,
    PricingIntegrityReportSummary,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_zone import ShippingProviderZone

from .helpers import count_brackets, count_province_members, list_province_members


def register(router: APIRouter) -> None:
    @router.get(
        "/ops/pricing-integrity/schemes/{scheme_id}",
        response_model=PricingIntegrityReportOut,
        status_code=status.HTTP_200_OK,
    )
    def ops_pricing_integrity_report(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        # 1) blocking: active=false 但仍占用 province members
        zones_archived = (
            db.query(ShippingProviderZone)
            .filter(
                ShippingProviderZone.scheme_id == scheme_id,
                ShippingProviderZone.active == False,  # noqa: E712
            )
            .order_by(ShippingProviderZone.id.asc())
            .all()
        )

        archived_occupying: list[PricingIntegrityArchivedZoneIssue] = []
        for z in zones_archived:
            provinces = list_province_members(db, zone_id=z.id)
            if not provinces:
                continue
            archived_occupying.append(
                PricingIntegrityArchivedZoneIssue(
                    scheme_id=scheme_id,
                    zone_id=z.id,
                    zone_name=z.name,
                    zone_active=bool(z.active),
                    province_members=provinces,
                    province_member_n=len(provinces),
                    suggested_action="ARCHIVE_RELEASE_PROVINCES",
                )
            )

        # 2) warning: released zones still have brackets
        zones_all = (
            db.query(ShippingProviderZone)
            .filter(ShippingProviderZone.scheme_id == scheme_id)
            .order_by(ShippingProviderZone.id.asc())
            .all()
        )

        released_still_priced: list[PricingIntegrityReleasedZoneStillPricedIssue] = []
        for z in zones_all:
            prov_n = count_province_members(db, zone_id=z.id)
            if prov_n != 0:
                continue
            br_n = count_brackets(db, zone_id=z.id)
            if br_n <= 0:
                continue
            released_still_priced.append(
                PricingIntegrityReleasedZoneStillPricedIssue(
                    scheme_id=scheme_id,
                    zone_id=z.id,
                    zone_name=z.name,
                    zone_active=bool(z.active),
                    province_member_n=prov_n,
                    brackets_n=br_n,
                    segment_template_id=getattr(z, "segment_template_id", None),
                    suggested_action="DETACH_ZONE_BRACKETS",
                )
            )

        # 3) warning: archived templates still referenced
        archived_templates = (
            db.query(ShippingProviderPricingSchemeSegmentTemplate)
            .filter(
                ShippingProviderPricingSchemeSegmentTemplate.scheme_id == scheme_id,
                ShippingProviderPricingSchemeSegmentTemplate.status == "archived",
            )
            .order_by(ShippingProviderPricingSchemeSegmentTemplate.id.asc())
            .all()
        )
        archived_tpl_by_id = {t.id: t for t in archived_templates}

        archived_template_referenced: list[PricingIntegrityArchivedTemplateStillReferencedIssue] = []
        if archived_tpl_by_id:
            tpl_ids = list(archived_tpl_by_id.keys())
            zones_ref = (
                db.query(ShippingProviderZone)
                .filter(
                    ShippingProviderZone.scheme_id == scheme_id,
                    ShippingProviderZone.segment_template_id.in_(tpl_ids),
                )
                .order_by(ShippingProviderZone.segment_template_id.asc(), ShippingProviderZone.id.asc())
                .all()
            )

            refs: dict[int, list[ShippingProviderZone]] = {}
            for z in zones_ref:
                tid = getattr(z, "segment_template_id", None)
                if tid is None:
                    continue
                refs.setdefault(int(tid), []).append(z)

            for tid, zs in refs.items():
                t = archived_tpl_by_id.get(tid)
                if t is None:
                    continue
                zone_ids = [int(x.id) for x in zs]
                zone_names = [str(x.name) for x in zs]
                archived_template_referenced.append(
                    PricingIntegrityArchivedTemplateStillReferencedIssue(
                        scheme_id=scheme_id,
                        template_id=int(t.id),
                        template_name=str(getattr(t, "name", "")),
                        template_status=str(getattr(t, "status", "")),
                        referencing_zone_ids=zone_ids,
                        referencing_zone_names=zone_names[:50],
                        referencing_zone_n=len(zone_ids),
                        suggested_action="UNBIND_ARCHIVED_TEMPLATE",
                    )
                )

        summary = PricingIntegrityReportSummary(
            blocking=len(archived_occupying),
            warning=len(released_still_priced) + len(archived_template_referenced),
        )
        return PricingIntegrityReportOut(
            scheme_id=scheme_id,
            summary=summary,
            archived_zones_still_occupying=archived_occupying,
            released_zones_still_priced=released_still_priced,
            archived_templates_still_referenced=archived_template_referenced,
        )
