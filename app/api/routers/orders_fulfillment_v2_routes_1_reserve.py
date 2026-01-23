# app/api/routers/orders_fulfillment_v2_routes_1_reserve.py
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.orders_fulfillment_v2_helpers import get_order_ref_and_trace_id
from app.api.routers.orders_fulfillment_v2_schemas import ReserveRequest, ReserveResponse
from app.services.order_fulfillment_manual_assign import manual_assign_fulfillment_warehouse
from app.services.order_service import OrderService


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
        "/{platform}/{shop_id}/{ext_order_no}/reserve",
        response_model=ReserveResponse,
    )
    async def order_reserve(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: ReserveRequest,
        session: AsyncSession = Depends(get_session),
    ):
        plat = platform.upper()

        if not body.lines:
            return ReserveResponse(
                status="OK",
                ref=f"ORD:{plat}:{shop_id}:{ext_order_no}",
                reservation_id=None,
                lines=0,
            )

        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        # Phase 5 合同护栏：
        # - 必须有明确执行仓 warehouse_id
        # - fulfillment_status 必须允许进入 reserve（READY_TO_FULFILL 或 MANUALLY_ASSIGNED）
        row = await session.execute(
            text(
                """
                SELECT warehouse_id, fulfillment_status, blocked_reasons, blocked_detail
                  FROM orders
                 WHERE platform = :p
                   AND shop_id  = :s
                   AND ext_order_no = :o
                 LIMIT 1
                """
            ),
            {"p": plat, "s": shop_id, "o": ext_order_no},
        )
        rec = row.first()
        if rec is None:
            raise HTTPException(409, detail=f"reserve blocked: order not found: {order_ref}")

        warehouse_id, fulfillment_status, blocked_reasons, blocked_detail = rec
        whid = int(warehouse_id) if warehouse_id is not None else None
        fstat = str(fulfillment_status or "")

        if whid is None or fstat not in ("READY_TO_FULFILL", "MANUALLY_ASSIGNED"):
            if fstat == "FULFILLMENT_BLOCKED":
                raise HTTPException(
                    409,
                    detail=f"reserve blocked: order is FULFILLMENT_BLOCKED; reasons={blocked_reasons}; detail={blocked_detail}",
                )
            raise HTTPException(
                409,
                detail=f"reserve blocked: order not READY_TO_FULFILL/MANUALLY_ASSIGNED or warehouse_id missing; status={fstat}, warehouse_id={whid}",
            )

        try:
            result = await OrderService.reserve(
                session,
                platform=plat,
                shop_id=shop_id,
                ref=order_ref,
                lines=[{"item_id": line.item_id, "qty": line.qty} for line in body.lines],
                trace_id=trace_id,
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(409, detail=str(e))
        except Exception:
            await session.rollback()
            raise

        return ReserveResponse(
            status=result.get("status", "OK"),
            ref=result.get("ref", order_ref),
            reservation_id=result.get("reservation_id"),
            lines=result.get("lines", len(body.lines)),
        )

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
        Phase 5.1：人工指定执行仓（唯一合法写 warehouse_id 的路径）

        - service 层写 orders.warehouse_id / fulfillment_warehouse_id
        - 写 fulfillment_status=MANUALLY_ASSIGNED
        - 写审计事件：MANUAL_WAREHOUSE_ASSIGNED
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

    # 兼容别名：旧 override 入口保留，但语义已等同于 manual-assign（避免前端/脚本断崖）
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
