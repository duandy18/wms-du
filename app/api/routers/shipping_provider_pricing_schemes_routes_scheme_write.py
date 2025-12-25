# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_write.py
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes_routes_scheme_helpers import seg_item_to_dict
from app.api.routers.shipping_provider_pricing_schemes_schemas import (
    SchemeCreateIn,
    SchemeDetailOut,
    SchemeUpdateIn,
    validate_default_pricing_mode,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import (
    check_perm,
    norm_nonempty,
    validate_effective_window,
    normalize_segments_json,
)
from app.db.deps import get_db
from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme


def register(router: APIRouter) -> None:
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
            segs_norm = normalize_segments_json(
                [seg_item_to_dict(x) for x in payload.segments_json]
            )
            segs_updated_at = datetime.now(tz=timezone.utc)

        sch = ShippingProviderPricingScheme(
            shipping_provider_id=provider_id,
            name=norm_nonempty(payload.name, "name"),
            active=bool(payload.active),
            priority=int(payload.priority),
            currency=(payload.currency or "CNY").strip() or "CNY",
            default_pricing_mode=dpm,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            billable_weight_rule=payload.billable_weight_rule,
            segments_json=segs_norm,
            segments_updated_at=segs_updated_at,
        )
        db.add(sch)
        db.commit()
        db.refresh(sch)

        return SchemeDetailOut(ok=True, data=to_scheme_out(sch, zones=[], surcharges=[]))

    @router.patch(
        "/pricing-schemes/{scheme_id}",
        response_model=SchemeDetailOut,
    )
    def update_scheme(
        scheme_id: int = Path(..., ge=1),
        payload: SchemeUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        data = payload.model_dump(exclude_unset=True)

        if "name" in data:
            sch.name = norm_nonempty(data.get("name"), "name")
        if "active" in data:
            sch.active = bool(data["active"])
        if "priority" in data:
            sch.priority = int(data["priority"])
        if "currency" in data:
            sch.currency = (data["currency"] or "CNY").strip() or "CNY"
        if "effective_from" in data:
            sch.effective_from = data["effective_from"]
        if "effective_to" in data:
            sch.effective_to = data["effective_to"]

        validate_effective_window(sch.effective_from, sch.effective_to)

        if "billable_weight_rule" in data:
            sch.billable_weight_rule = data["billable_weight_rule"]

        # ✅ 修改默认口径：强校验（不允许 manual_quote）
        if "default_pricing_mode" in data:
            try:
                sch.default_pricing_mode = validate_default_pricing_mode(
                    data["default_pricing_mode"]
                )
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

        # ✅ Phase 4.3：列结构写回（强校验 + 更新时间）
        if "segments_json" in data:
            raw = data["segments_json"]
            if raw is None:
                sch.segments_json = None
                sch.segments_updated_at = None
            else:
                segs_norm = normalize_segments_json([seg_item_to_dict(x) for x in raw])
                sch.segments_json = segs_norm
                sch.segments_updated_at = datetime.now(tz=timezone.utc)

        db.commit()
        db.refresh(sch)

        # 返回“聚合详情”（zones/surcharges）
        sch2, zones, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(
            ok=True, data=to_scheme_out(sch2, zones=zones, surcharges=surcharges)
        )
