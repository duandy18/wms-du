# app/oms/orders/routers/order_outbound_options.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.oms.orders.contracts.order_outbound_options import (
    OrderOutboundOptionOut,
    OrderOutboundOptionsOut,
)
from app.oms.orders.repos.order_outbound_options_repo import (
    list_order_outbound_options,
)

router = APIRouter(tags=["oms-order-outbound-options"])


@router.get(
    "/orders/outbound-options",
    response_model=OrderOutboundOptionsOut,
)
async def get_order_outbound_options(
    q: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    store_code: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> OrderOutboundOptionsOut:
    data = await list_order_outbound_options(
        session,
        q=q,
        platform=platform,
        store_code=store_code,
        limit=int(limit),
        offset=int(offset),
    )

    return OrderOutboundOptionsOut(
        items=[OrderOutboundOptionOut(**x) for x in data["items"]],
        total=int(data["total"]),
        limit=int(data["limit"]),
        offset=int(data["offset"]),
    )
