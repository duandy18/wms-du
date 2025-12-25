# app/api/routers/orders_fulfillment_v2_routes_1_reserve.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.orders_fulfillment_v2_helpers import get_order_ref_and_trace_id
from app.api.routers.orders_fulfillment_v2_schemas import ReserveRequest, ReserveResponse
from app.services.order_service import OrderService


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
