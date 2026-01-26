# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_write.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
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
    segments_norm_to_rows,
)
from app.db.deps import get_db
from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_segment import ShippingProviderPricingSchemeSegment


class SchemeSegmentActivePatchIn(BaseModel):
    active: bool


def _replace_segments_table(db: Session, scheme_id: int, segs_norm: Optional[list]) -> None:
    """
    将 segs_norm（normalize_segments_json 的输出）落到段表：
    - v1：delete + insert（最稳、最简单）
    - active 默认 true（暂停由专门 endpoint 管）
    """
    db.query(ShippingProviderPricingSchemeSegment).filter(
        ShippingProviderPricingSchemeSegment.scheme_id == scheme_id
    ).delete(synchronize_session=False)

    if not segs_norm:
        return

    rows = segments_norm_to_rows(segs_norm)
    for ord_i, mn, mx in rows:
        db.add(
            ShippingProviderPricingSchemeSegment(
                scheme_id=scheme_id,
                ord=int(ord_i),
                min_kg=mn,
                max_kg=mx,
                active=True,
            )
        )


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
            segs_norm = normalize_segments_json([seg_item_to_dict(x) for x in payload.segments_json])
            segs_updated_at = datetime.now(tz=timezone.utc)

        sch = ShippingProviderPricingScheme(
            shipping_provider_id=provider_id,
            name=norm_nonempty(payload.name, "name"),
            active=bool(payload.active),
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

        # ✅ 同步落段表（新能力）
        if segs_norm is not None:
            _replace_segments_table(db, sch.id, segs_norm)
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

        # ✅ Pydantic v2：用 fields_set 判断“客户端是否传了某字段”
        fields_set = payload.model_fields_set

        data = payload.model_dump(exclude_unset=True)

        if "name" in data:
            sch.name = norm_nonempty(data.get("name"), "name")

        if "active" in data:
            sch.active = bool(data["active"])

        # ✅ 归档（关键修复）：不要依赖 model_dump 是否包含 archived_at
        # - 客户端传 archived_at（即使是 null）=> 进入这里
        if "archived_at" in fields_set:
            sch.archived_at = payload.archived_at
            # 归档时强制停用（坚持你定的原则：归档必须是停运态）
            if sch.archived_at is not None:
                sch.active = False

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
                sch.default_pricing_mode = validate_default_pricing_mode(data["default_pricing_mode"])
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

        # ✅ Phase 4.3：列结构写回（强校验 + 更新时间） + 同步段表
        if "segments_json" in data:
            raw = data["segments_json"]
            if raw is None:
                sch.segments_json = None
                sch.segments_updated_at = None
                _replace_segments_table(db, scheme_id, None)
            else:
                segs_norm = normalize_segments_json([seg_item_to_dict(x) for x in raw])
                sch.segments_json = segs_norm
                sch.segments_updated_at = datetime.now(tz=timezone.utc)
                _replace_segments_table(db, scheme_id, segs_norm)

        db.commit()
        db.refresh(sch)

        sch2, zones, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(ok=True, data=to_scheme_out(sch2, zones=zones, surcharges=surcharges))

    # ✅ 新增：切换某个段的 active（用于前端“暂停使用”）
    @router.patch(
        "/pricing-schemes/{scheme_id}/segments/{segment_id}",
        response_model=SchemeDetailOut,
    )
    def patch_scheme_segment_active(
        scheme_id: int = Path(..., ge=1),
        segment_id: int = Path(..., ge=1),
        payload: SchemeSegmentActivePatchIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = db.get(ShippingProviderPricingScheme, scheme_id)
        if not sch:
            raise HTTPException(status_code=404, detail="Scheme not found")

        seg = db.get(ShippingProviderPricingSchemeSegment, segment_id)
        if not seg or seg.scheme_id != scheme_id:
            raise HTTPException(status_code=404, detail="Scheme segment not found")

        seg.active = bool(payload.active)
        db.commit()

        sch2, zones, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(ok=True, data=to_scheme_out(sch2, zones=zones, surcharges=surcharges))
