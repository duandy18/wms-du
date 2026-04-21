from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.inventory_adjustment.inbound_reversal.contracts.inbound_reversal import (
    InboundReversalIn,
    InboundReversalOut,
)
from app.wms.inventory_adjustment.inbound_reversal.services.inbound_reversal_service import (
    reverse_inbound_event,
)

router = APIRouter(prefix="/wms/inbound", tags=["wms-inbound-reversal"])


@router.post("/events/{event_id}/reverse", response_model=InboundReversalOut)
async def reverse_inbound_event_endpoint(
    event_id: int,
    payload: InboundReversalIn,
    session: AsyncSession = Depends(get_session),
) -> InboundReversalOut:
    try:
        out = await reverse_inbound_event(
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
