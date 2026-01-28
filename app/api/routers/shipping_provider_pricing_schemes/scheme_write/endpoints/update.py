from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_scheme_out
from app.api.routers.shipping_provider_pricing_schemes_query_helpers import load_scheme_entities
from app.api.routers.shipping_provider_pricing_schemes_routes_scheme_helpers import seg_item_to_dict
from app.api.routers.shipping_provider_pricing_schemes_schemas import (
    SchemeDetailOut,
    SchemeUpdateIn,
    validate_default_pricing_mode,
)
from app.api.routers.shipping_provider_pricing_schemes_utils import (
    check_perm,
    norm_nonempty,
    normalize_segments_json,
    validate_effective_window,
)
from app.db.deps import get_db
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme

from ..shared import replace_segments_table


def _activate_scheme_exclusive(db: Session, scheme_id: int) -> ShippingProviderPricingScheme:
    """
    ✅ 系统级裁决：同一 shipping_provider_id 下，任意时刻只能有一个 active=true（且 archived_at is null）。

    实现方式：
    - 在一个事务内：
      1) 锁住同 provider 的 schemes（避免并发互踩）
      2) 停用其它 active=true
      3) 启用目标 scheme
    - DB 层再加 partial unique index 做铁门兜底（见 migration）
    """
    sch = (
        db.query(ShippingProviderPricingScheme)
        .filter(ShippingProviderPricingScheme.id == scheme_id)
        .with_for_update()
        .one_or_none()
    )
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")

    if sch.archived_at is not None:
        raise HTTPException(status_code=400, detail="Archived scheme cannot be activated")

    provider_id = int(sch.shipping_provider_id)

    # ✅ provider 级别锁：锁住该 provider 下所有 schemes，避免并发下出现短暂多活/互相覆盖
    (
        db.query(ShippingProviderPricingScheme.id)
        .filter(ShippingProviderPricingScheme.shipping_provider_id == provider_id)
        .with_for_update()
        .all()
    )

    # 1) 停用其它 active=true（只对未归档的参与竞选；归档的本身也应当是 inactive）
    db.execute(
        update(ShippingProviderPricingScheme)
        .where(
            ShippingProviderPricingScheme.shipping_provider_id == provider_id,
            ShippingProviderPricingScheme.id != scheme_id,
            ShippingProviderPricingScheme.archived_at.is_(None),
            ShippingProviderPricingScheme.active.is_(True),
        )
        .values(active=False)
    )

    # 2) 启用目标
    sch.active = True
    return sch


def register_update_routes(router: APIRouter) -> None:
    @router.post(
        "/pricing-schemes/{scheme_id}/activate-exclusive",
        response_model=SchemeDetailOut,
    )
    def activate_scheme_exclusive(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        """
        ✅ 原子“独占启用”接口：
        - 启用本 scheme
        - 同 provider 其它 scheme 自动停用
        """
        check_perm(db, user, "config.store.write")

        sch = _activate_scheme_exclusive(db, scheme_id)

        db.commit()
        db.refresh(sch)

        sch2, zones, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(ok=True, data=to_scheme_out(sch2, zones=zones, surcharges=surcharges))

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

        # ✅ 归档（关键修复）：不要依赖 model_dump 是否包含 archived_at
        if "archived_at" in fields_set:
            sch.archived_at = payload.archived_at
            if sch.archived_at is not None:
                sch.active = False

        # ✅ active（系统裁决：不再允许多活）
        if "active" in data:
            next_active = bool(data["active"])
            if next_active:
                # 归档不能启用
                if sch.archived_at is not None:
                    raise HTTPException(status_code=400, detail="Archived scheme cannot be activated")
                # ✅ 走独占启用（原子逻辑）
                _activate_scheme_exclusive(db, scheme_id)
            else:
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
                replace_segments_table(db, scheme_id, None)
            else:
                segs_norm = normalize_segments_json([seg_item_to_dict(x) for x in raw])
                sch.segments_json = segs_norm
                sch.segments_updated_at = datetime.now(tz=timezone.utc)
                replace_segments_table(db, scheme_id, segs_norm)

        db.commit()
        db.refresh(sch)

        sch2, zones, surcharges = load_scheme_entities(db, scheme_id)
        return SchemeDetailOut(ok=True, data=to_scheme_out(sch2, zones=zones, surcharges=surcharges))
