from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.inventory_adjustment.outbound_reversal.contracts.outbound_reversal import (
    OutboundReversalIn,
    OutboundReversalOut,
)
from app.wms.inventory_adjustment.outbound_reversal.services.outbound_reversal_service import (
    reverse_outbound_event,
)

router = APIRouter(prefix="/wms/outbound", tags=["wms-outbound-reversal"])


@router.post("/events/{event_id}/reverse", response_model=OutboundReversalOut)
async def reverse_outbound_event_endpoint(
    event_id: int,
    payload: OutboundReversalIn,
    session: AsyncSession = Depends(get_session),
) -> OutboundReversalOut:
    try:
        out = await reverse_outbound_event(
            session,
            event_id=int(event_id),
            payload=payload,
            user_id=None,
        )
        await session.commit()
        return out
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


__all__ = ["router"]
