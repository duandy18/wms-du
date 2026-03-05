# app/api/routers/pricing_integrity/cleanup.py
from __future__ import annotations

from typing import List, Tuple

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_segment_template import ShippingProviderPricingSchemeSegmentTemplate
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge
from app.models.shipping_provider_zone import ShippingProviderZone


# 这些表你在 SQL 里已经用过，说明项目里存在
from app.models.shipping_provider_pricing_scheme_segment import ShippingProviderPricingSchemeSegment  # type: ignore
from app.models.shipping_provider_pricing_scheme_warehouse import ShippingProviderPricingSchemeWarehouse  # type: ignore
from app.models.shipping_provider_pricing_scheme_segment_template_item import (
    ShippingProviderPricingSchemeSegmentTemplateItem,
)


class ShellSchemeRow(BaseModel):
    scheme_id: int
    name: str
    active: bool
    tpl_n: int = 0
    surcharge_n: int = 0
    seg_n: int = 0
    wh_n: int = 0
    zone_n: int = 0


class CleanupShellSchemesOut(BaseModel):
    ok: bool = True
    dry_run: bool
    include_surcharge_only: bool
    limit: int
    candidates_n: int
    deleted_n: int = 0
    candidates: List[ShellSchemeRow] = Field(default_factory=list)


def _counts_for_scheme(db: Session, scheme_id: int) -> Tuple[int, int, int, int, int]:
    tpl_n = db.query(ShippingProviderPricingSchemeSegmentTemplate.id).filter(
        ShippingProviderPricingSchemeSegmentTemplate.scheme_id == scheme_id
    ).count()
    surcharge_n = db.query(ShippingProviderSurcharge.id).filter(ShippingProviderSurcharge.scheme_id == scheme_id).count()
    seg_n = db.query(ShippingProviderPricingSchemeSegment.id).filter(ShippingProviderPricingSchemeSegment.scheme_id == scheme_id).count()
    wh_n = db.query(ShippingProviderPricingSchemeWarehouse.id).filter(
        ShippingProviderPricingSchemeWarehouse.scheme_id == scheme_id
    ).count()
    zone_n = db.query(ShippingProviderZone.id).filter(ShippingProviderZone.scheme_id == scheme_id).count()
    return tpl_n, surcharge_n, seg_n, wh_n, zone_n


def register(router: APIRouter) -> None:
    @router.post(
        "/ops/pricing-integrity/cleanup/shell-schemes",
        response_model=CleanupShellSchemesOut,
        status_code=status.HTTP_200_OK,
    )
    def cleanup_shell_schemes(
        dry_run: bool = Query(True),
        limit: int = Query(500, ge=1, le=5000),
        include_surcharge_only: bool = Query(False),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        # 运维动作：用写权限挡住误操作
        check_perm(db, user, "config.store.write")

        # 只扫 inactive（避免误伤活跃方案）
        schemes = (
            db.query(ShippingProviderPricingScheme)
            .filter(ShippingProviderPricingScheme.active.is_(False))
            .order_by(ShippingProviderPricingScheme.id.desc())
            .limit(limit)
            .all()
        )

        candidates: List[ShellSchemeRow] = []
        for s in schemes:
            tpl_n, surcharge_n, seg_n, wh_n, zone_n = _counts_for_scheme(db, int(s.id))

            is_shell = (tpl_n == 0 and seg_n == 0 and wh_n == 0 and zone_n == 0 and surcharge_n == 0)
            is_surcharge_only = (tpl_n == 0 and seg_n == 0 and wh_n == 0 and zone_n == 0 and surcharge_n > 0)

            if is_shell or (include_surcharge_only and is_surcharge_only):
                candidates.append(
                    ShellSchemeRow(
                        scheme_id=int(s.id),
                        name=str(getattr(s, "name", "")),
                        active=bool(getattr(s, "active", False)),
                        tpl_n=tpl_n,
                        surcharge_n=surcharge_n,
                        seg_n=seg_n,
                        wh_n=wh_n,
                        zone_n=zone_n,
                    )
                )

        if dry_run:
            return CleanupShellSchemesOut(
                dry_run=True,
                include_surcharge_only=include_surcharge_only,
                limit=limit,
                candidates_n=len(candidates),
                deleted_n=0,
                candidates=candidates[:200],  # 防止响应过大
            )

        # 执行删除：先删子表，再删 scheme（同你手工清理顺序）
        deleted_n = 0
        for row in candidates:
            sid = row.scheme_id

            # 1) surcharges
            db.query(ShippingProviderSurcharge).filter(ShippingProviderSurcharge.scheme_id == sid).delete(
                synchronize_session=False
            )

            # 2) segments
            db.query(ShippingProviderPricingSchemeSegment).filter(ShippingProviderPricingSchemeSegment.scheme_id == sid).delete(
                synchronize_session=False
            )

            # 3) warehouses
            db.query(ShippingProviderPricingSchemeWarehouse).filter(
                ShippingProviderPricingSchemeWarehouse.scheme_id == sid
            ).delete(synchronize_session=False)

            # 4) template items via templates
            tpl_ids = [
                int(x[0])
                for x in db.query(ShippingProviderPricingSchemeSegmentTemplate.id)
                .filter(ShippingProviderPricingSchemeSegmentTemplate.scheme_id == sid)
                .all()
            ]
            if tpl_ids:
                db.query(ShippingProviderPricingSchemeSegmentTemplateItem).filter(
                    ShippingProviderPricingSchemeSegmentTemplateItem.template_id.in_(tpl_ids)
                ).delete(synchronize_session=False)

            # 5) templates
            db.query(ShippingProviderPricingSchemeSegmentTemplate).filter(
                ShippingProviderPricingSchemeSegmentTemplate.scheme_id == sid
            ).delete(synchronize_session=False)

            # 6) zones（理论上为 0，但写上更稳）
            db.query(ShippingProviderZone).filter(ShippingProviderZone.scheme_id == sid).delete(synchronize_session=False)

            # 7) scheme
            db.query(ShippingProviderPricingScheme).filter(
                ShippingProviderPricingScheme.id == sid,
                ShippingProviderPricingScheme.active.is_(False),
            ).delete(synchronize_session=False)

            deleted_n += 1

        db.commit()

        return CleanupShellSchemesOut(
            dry_run=False,
            include_surcharge_only=include_surcharge_only,
            limit=limit,
            candidates_n=len(candidates),
            deleted_n=deleted_n,
            candidates=candidates[:200],
        )
