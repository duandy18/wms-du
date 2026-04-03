# app/tms/pricing/bindings/runtime_routes.py
#
# 分拆说明：
# - 本文件从原 routes.py 中拆出 bindings 运行控制接口。
# - 当前只负责：
#   1) activate（立即启用 / 定时启用）
#   2) deactivate（停用）
# - 维护约束：
#   - 不在本文件中处理绑定模板/换绑模板
#   - activate 只做运行层轻校验，不做“模板已被 binding 使用”唯一性校验

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.tms.permissions import check_config_perm
from app.tms.pricing.bindings.contracts import (
    WarehouseShippingProviderActivateIn,
    WarehouseShippingProviderActivateOut,
    WarehouseShippingProviderDeactivateOut,
)
from app.tms.pricing.bindings.helpers import row_to_out
from app.tms.pricing.bindings.read_routes import _load_binding_row_or_404
from app.tms.pricing.bindings.validators import (
    _ensure_activation_template_allowed,
)

router = APIRouter()


@router.post(
    "/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/activate",
    response_model=WarehouseShippingProviderActivateOut,
    name="pricing_activate_warehouse_binding",
)
async def pricing_activate_warehouse_binding(
    warehouse_id: int = Path(..., ge=1),
    shipping_provider_id: int = Path(..., ge=1),
    payload: WarehouseShippingProviderActivateIn = ...,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseShippingProviderActivateOut:
    check_config_perm(db, current_user, ["config.store.write"])

    existing = (
        await session.execute(
            text(
                """
                SELECT shipping_provider_id, active_template_id
                FROM warehouse_shipping_providers
                WHERE warehouse_id = :wid
                  AND shipping_provider_id = :pid
                """
            ),
            {"wid": warehouse_id, "pid": shipping_provider_id},
        )
    ).mappings().first()

    if not existing:
        raise HTTPException(status_code=404, detail="warehouse_shipping_provider not found")

    active_template_id = existing.get("active_template_id")
    if active_template_id is None:
        raise HTTPException(
            status_code=409, detail="active_template_id required before activation"
        )

    await _ensure_activation_template_allowed(
        session,
        db,
        shipping_provider_id=shipping_provider_id,
        active_template_id=int(active_template_id),
    )

    effective_from = payload.effective_from or datetime.now(timezone.utc)

    await session.execute(
        text(
            """
            UPDATE warehouse_shipping_providers
               SET active = true,
                   effective_from = :effective_from,
                   disabled_at = NULL
             WHERE warehouse_id = :wid
               AND shipping_provider_id = :pid
            """
        ),
        {
            "wid": warehouse_id,
            "pid": shipping_provider_id,
            "effective_from": effective_from,
        },
    )

    await session.commit()

    binding_row = await _load_binding_row_or_404(
        session,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
    )
    return WarehouseShippingProviderActivateOut(ok=True, data=row_to_out(binding_row))


@router.post(
    "/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/deactivate",
    response_model=WarehouseShippingProviderDeactivateOut,
    name="pricing_deactivate_warehouse_binding",
)
async def pricing_deactivate_warehouse_binding(
    warehouse_id: int = Path(..., ge=1),
    shipping_provider_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseShippingProviderDeactivateOut:
    check_config_perm(db, current_user, ["config.store.write"])

    row = (
        await session.execute(
            text(
                """
                UPDATE warehouse_shipping_providers
                   SET active = false,
                       disabled_at = :disabled_at
                 WHERE warehouse_id = :wid
                   AND shipping_provider_id = :pid
                RETURNING warehouse_id, shipping_provider_id
                """
            ),
            {
                "wid": warehouse_id,
                "pid": shipping_provider_id,
                "disabled_at": datetime.now(timezone.utc),
            },
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="warehouse_shipping_provider not found")

    await session.commit()

    binding_row = await _load_binding_row_or_404(
        session,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
    )
    return WarehouseShippingProviderDeactivateOut(ok=True, data=row_to_out(binding_row))
