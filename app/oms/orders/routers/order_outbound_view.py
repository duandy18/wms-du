# app/oms/orders/routers/order_outbound_view.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.oms.orders.contracts.order_outbound_view import (
    OrderOutboundViewLineOut,
    OrderOutboundViewOrderOut,
    OrderOutboundViewResponse,
)
from app.oms.orders.repos.order_outbound_view_repo import (
    load_order_outbound_head,
    load_order_outbound_lines,
)

router = APIRouter(tags=["oms-order-outbound-view"])


@router.get(
    "/orders/{order_id}/outbound-view",
    response_model=OrderOutboundViewResponse,
)
async def get_order_outbound_view(
    order_id: int,
    session: AsyncSession = Depends(get_session),
) -> OrderOutboundViewResponse:
    head = await load_order_outbound_head(session, order_id=int(order_id))
    lines = await load_order_outbound_lines(session, order_id=int(order_id))

    return OrderOutboundViewResponse(
        ok=True,
        order=OrderOutboundViewOrderOut(**head),
        lines=[OrderOutboundViewLineOut(**x) for x in lines],
    )
