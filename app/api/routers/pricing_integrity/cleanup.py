# app/api/routers/pricing_integrity/cleanup.py
from __future__ import annotations

from typing import List, Tuple

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge_config import ShippingProviderSurchargeConfig
from app.models.shipping_provider_surcharge_config_city import ShippingProviderSurchargeConfigCity


class ShellSchemeRow(BaseModel):
    scheme_id: int
    name: str
    active: bool

    # 终态主线统计
    group_n: int = 0
    matrix_n: int = 0
    surcharge_n: int = 0
    seg_n: int = 0
    wh_n: int = 0

    # 兼容字段：保留输出结构稳定，但已固定为 0
    tpl_n: int = 0
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
    """
    终态主线（硬仓库边界）：
    - scheme 自带 warehouse_id，不再统计绑定行
    - 主线实体：destination_groups / pricing_matrix / surcharge_configs(+cities)
    - seg_n 保留输出字段，但固定为 0
    """
    group_n = (
        db.query(ShippingProviderDestinationGroup.id)
        .filter(ShippingProviderDestinationGroup.scheme_id == scheme_id)
        .count()
    )
    matrix_n = (
        db.query(ShippingProviderPricingMatrix.id)
        .join(
            ShippingProviderDestinationGroup,
            ShippingProviderDestinationGroup.id == ShippingProviderPricingMatrix.group_id,
        )
        .filter(ShippingProviderDestinationGroup.scheme_id == scheme_id)
        .count()
    )
    surcharge_n = (
        db.query(ShippingProviderSurchargeConfig.id)
        .filter(ShippingProviderSurchargeConfig.scheme_id == scheme_id)
        .count()
    )
    seg_n = 0
    wh_n = 0
    return group_n, matrix_n, surcharge_n, seg_n, wh_n


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
        check_perm(db, user, "config.store.write")

        schemes = (
            db.query(ShippingProviderPricingScheme)
            .filter(ShippingProviderPricingScheme.active.is_(False))
            .order_by(ShippingProviderPricingScheme.id.desc())
            .limit(limit)
            .all()
        )

        candidates: List[ShellSchemeRow] = []
        for s in schemes:
            group_n, matrix_n, surcharge_n, seg_n, wh_n = _counts_for_scheme(db, int(s.id))

            is_shell = (group_n == 0 and matrix_n == 0 and seg_n == 0 and surcharge_n == 0)
            is_surcharge_only = (group_n == 0 and matrix_n == 0 and seg_n == 0 and surcharge_n > 0)

            if is_shell or (include_surcharge_only and is_surcharge_only):
                candidates.append(
                    ShellSchemeRow(
                        scheme_id=int(s.id),
                        name=str(getattr(s, "name", "")),
                        active=bool(getattr(s, "active", False)),
                        group_n=group_n,
                        matrix_n=matrix_n,
                        surcharge_n=surcharge_n,
                        seg_n=seg_n,
                        wh_n=wh_n,
                        tpl_n=0,
                        zone_n=0,
                    )
                )

        if dry_run:
            return CleanupShellSchemesOut(
                dry_run=True,
                include_surcharge_only=include_surcharge_only,
                limit=limit,
                candidates_n=len(candidates),
                deleted_n=0,
                candidates=candidates[:200],
            )

        deleted_n = 0
        for row in candidates:
            sid = row.scheme_id

            group_ids = [
                int(x[0])
                for x in db.query(ShippingProviderDestinationGroup.id)
                .filter(ShippingProviderDestinationGroup.scheme_id == sid)
                .all()
            ]

            if group_ids:
                db.query(ShippingProviderPricingMatrix).filter(
                    ShippingProviderPricingMatrix.group_id.in_(group_ids)
                ).delete(synchronize_session=False)

                db.query(ShippingProviderDestinationGroup).filter(
                    ShippingProviderDestinationGroup.id.in_(group_ids)
                ).delete(synchronize_session=False)

            config_ids = [
                int(x[0])
                for x in db.query(ShippingProviderSurchargeConfig.id)
                .filter(ShippingProviderSurchargeConfig.scheme_id == sid)
                .all()
            ]

            if config_ids:
                db.query(ShippingProviderSurchargeConfigCity).filter(
                    ShippingProviderSurchargeConfigCity.config_id.in_(config_ids)
                ).delete(synchronize_session=False)

                db.query(ShippingProviderSurchargeConfig).filter(
                    ShippingProviderSurchargeConfig.id.in_(config_ids)
                ).delete(synchronize_session=False)

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
