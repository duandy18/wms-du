# app/wms/outbound/routers/order_submit.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import new_trace
from app.db.deps import get_async_session as get_session
from app.user.deps.auth import get_current_user
from app.wms.outbound.contracts.order_submit import (
    OrderOutboundSubmitIn,
    OrderOutboundSubmitOut,
)
from app.wms.outbound.services.outbound_event_submit_service import (
    submit_order_outbound_event,
)

router = APIRouter(prefix="/wms/outbound", tags=["wms-outbound-order-submit"])


@router.post(
    "/orders/{order_id}/submit",
    response_model=OrderOutboundSubmitOut,
)
async def submit_order_outbound(
    order_id: int,
    payload: OrderOutboundSubmitIn,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> OrderOutboundSubmitOut:
    trace = new_trace("http:/wms/outbound/orders/submit")

    try:
        result = await submit_order_outbound_event(
            session,
            order_id=int(order_id),
            warehouse_id=int(payload.warehouse_id),
            operator_id=getattr(user, "id", None),
            trace_id=trace.trace_id,
            payload=payload,
        )
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        await session.rollback()
        raise
