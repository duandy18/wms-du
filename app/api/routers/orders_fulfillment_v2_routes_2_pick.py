# app/api/routers/orders_fulfillment_v2_routes_2_pick.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.orders_fulfillment_v2_helpers import get_order_ref_and_trace_id
from app.api.routers.orders_fulfillment_v2_schemas import PickRequest, PickResponse
from app.services.pick_service import PickService
from app.services.soft_reserve_service import SoftReserveService


def register(router: APIRouter) -> None:
    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/pick",
        response_model=List[PickResponse],
    )
    async def order_pick(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: PickRequest,
        session: AsyncSession = Depends(get_session),
    ):
        plat = platform.upper()

        if not body.lines:
            return []

        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=plat,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        svc = PickService()
        soft_reserve = SoftReserveService()
        occurred_at = body.occurred_at or datetime.now(timezone.utc)

        responses: List[PickResponse] = []
        ref_line = 1

        try:
            for line in body.lines:
                result = await svc.record_pick(
                    session=session,
                    item_id=line.item_id,
                    qty=line.qty,
                    ref=order_ref,
                    occurred_at=occurred_at,
                    batch_code=body.batch_code,
                    warehouse_id=body.warehouse_id,
                    trace_id=trace_id,
                    start_ref_line=ref_line,
                )
                ref_line = result.get("ref_line", ref_line) + 1

                responses.append(
                    PickResponse(
                        item_id=line.item_id,
                        warehouse_id=result.get("warehouse_id", body.warehouse_id),
                        batch_code=result.get("batch_code", body.batch_code),
                        picked=result.get("picked", line.qty),
                        stock_after=result.get("stock_after"),
                        ref=result.get("ref", order_ref),
                        status=result.get("status", "OK"),
                    )
                )

            await soft_reserve.pick_consume(
                session=session,
                platform=plat,
                shop_id=shop_id,
                warehouse_id=body.warehouse_id,
                ref=order_ref,
                occurred_at=occurred_at,
                trace_id=trace_id,
            )

            await session.commit()

        except ValueError as e:
            await session.rollback()
            raise HTTPException(409, detail=str(e))
        except Exception:
            await session.rollback()
            raise

        return responses
