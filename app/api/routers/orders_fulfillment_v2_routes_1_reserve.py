# app/api/routers/orders_fulfillment_v2_routes_1_reserve.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.orders_fulfillment_v2_helpers import get_order_ref_and_trace_id
from app.services.order_fulfillment_manual_assign import manual_assign_fulfillment_warehouse


class ManualAssignRequest(BaseModel):
    """
    Phase 5.1：人工指定执行仓（执行期履约决策）
    """

    warehouse_id: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1, max_length=500)
    note: Optional[str] = Field(default=None, max_length=1000)


class ManualAssignResponse(BaseModel):
    status: str
    ref: str
    from_warehouse_id: Optional[int] = None
    to_warehouse_id: int
    fulfillment_status: str


def register(router: APIRouter) -> None:
    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/fulfillment/manual-assign",
        response_model=ManualAssignResponse,
    )
    async def fulfillment_manual_assign(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: ManualAssignRequest,
        session: AsyncSession = Depends(get_session),
        user: Any = Depends(get_current_user),
    ):
        """
        Phase 5.1：人工指定执行仓（执行期唯一合法写入路径）

        ✅ 新世界观（一步到位迁移后）：
        - 实际出库仓写入 order_fulfillment.actual_warehouse_id（执行仓事实）
        - planned/service 归属仓仍由 routing 写入 order_fulfillment.planned_warehouse_id
        - 写 fulfillment_status=MANUALLY_ASSIGNED
        - 写审计事件：MANUAL_WAREHOUSE_ASSIGNED

        ❌ 禁止回潮：
        - 不允许写 orders.warehouse_id（该列迁移后将被删除/不再承载事实）
        """
        plat = platform.upper()
        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        operator_id = getattr(user, "id", None)

        try:
            r = await manual_assign_fulfillment_warehouse(
                session,
                platform=plat,
                shop_id=shop_id,
                ext_order_no=ext_order_no,
                order_ref=order_ref,
                trace_id=trace_id,
                warehouse_id=int(body.warehouse_id),
                reason=body.reason,
                note=body.note,
                operator_id=int(operator_id) if operator_id is not None else None,
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(409, detail=str(e))
        except Exception:
            await session.rollback()
            raise

        return ManualAssignResponse(
            status="OK",
            ref=order_ref,
            from_warehouse_id=r.from_warehouse_id,
            to_warehouse_id=r.to_warehouse_id,
            fulfillment_status=r.fulfillment_status,
        )

    # 兼容别名：旧 override 入口保留，但语义等同于 manual-assign
    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/fulfillment/override",
        response_model=ManualAssignResponse,
    )
    async def fulfillment_override_alias(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: ManualAssignRequest,
        session: AsyncSession = Depends(get_session),
        user: Any = Depends(get_current_user),
    ):
        return await fulfillment_manual_assign(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            body=body,
            session=session,
            user=user,
        )
