from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_routes_scheme_helpers import seg_item_to_dict
from app.api.routers.shipping_provider_pricing_schemes.schemas import (
    SchemeCreateIn,
    SchemeDetailOut,
)
from app.api.routers.shipping_provider_pricing_schemes.validators import (
    validate_default_pricing_mode,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import (
    check_perm,
    norm_nonempty,
    normalize_segments_json,
    validate_effective_window,
)
from app.db.deps import get_db
from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme

from ..shared import replace_segments_table


def register_create_routes(router: APIRouter) -> None:
    @router.post(
        "/shipping-providers/{provider_id}/pricing-schemes",
        response_model=SchemeDetailOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_scheme(
        provider_id: int = Path(..., ge=1),
        payload: SchemeCreateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        provider = db.get(ShippingProvider, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="ShippingProvider not found")

        validate_effective_window(payload.effective_from, payload.effective_to)

        # ✅ 方案默认口径：强校验（不允许 manual_quote）
        try:
            dpm = validate_default_pricing_mode(payload.default_pricing_mode)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        segs_norm = None
        segs_updated_at = None
        if payload.segments_json is not None:
            segs_norm = normalize_segments_json([seg_item_to_dict(x) for x in payload.segments_json])
            segs_updated_at = datetime.now(tz=timezone.utc)

        # ✅ 系统裁决：同一 provider 未归档 schemes 任意时刻只能一个 active=true
        # - DB 已有 partial unique index 兜底
        # - 这里做应用层原子互斥：若本次创建要生效，则先停用其它 active=true
        next_active = bool(payload.active)

        if next_active:
            # provider scope lock：锁住该 provider 的所有 schemes，避免并发下互踩
            (
                db.query(ShippingProviderPricingScheme.id)
                .filter(ShippingProviderPricingScheme.shipping_provider_id == provider_id)
                .with_for_update()
                .all()
            )

            # 先停用其它 active=true（只对未归档参与竞选）
            db.execute(
                update(ShippingProviderPricingScheme)
                .where(
                    ShippingProviderPricingScheme.shipping_provider_id == provider_id,
                    ShippingProviderPricingScheme.archived_at.is_(None),
                    ShippingProviderPricingScheme.active.is_(True),
                )
                .values(active=False)
            )

        sch = ShippingProviderPricingScheme(
            shipping_provider_id=provider_id,
            name=norm_nonempty(payload.name, "name"),
            active=next_active,
            currency=(payload.currency or "CNY").strip() or "CNY",
            default_pricing_mode=dpm,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            billable_weight_rule=payload.billable_weight_rule,
            segments_json=segs_norm,
            segments_updated_at=segs_updated_at,
            default_segment_template_id=None,
        )
        db.add(sch)
        db.commit()
        db.refresh(sch)

        # ✅ 同步落段表（新能力）
        if segs_norm is not None:
            replace_segments_table(db, sch.id, segs_norm)
            db.commit()
            db.refresh(sch)

        return SchemeDetailOut(ok=True, data=to_scheme_out(sch, zones=[], surcharges=[]))
