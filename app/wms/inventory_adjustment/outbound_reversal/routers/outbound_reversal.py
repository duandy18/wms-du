from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.inventory_adjustment.outbound_reversal.contracts.outbound_reversal import (
    OutboundReversalDetailOut,
    OutboundReversalIn,
    OutboundReversalOptionsOut,
    OutboundReversalOut,
    OutboundReversalSourceType,
)
from app.wms.inventory_adjustment.outbound_reversal.services.outbound_reversal_service import (
    get_outbound_reversal_detail,
    list_outbound_reversal_options,
    reverse_outbound_event,
)

router = APIRouter(
    prefix="/inventory-adjustment/outbound-reversal",
    tags=["inventory-adjustment-outbound-reversal"],
)


@router.get("/options", response_model=OutboundReversalOptionsOut)
async def list_outbound_reversal_options_endpoint(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=100, ge=1, le=200),
    source_type: OutboundReversalSourceType | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> OutboundReversalOptionsOut:
    return await list_outbound_reversal_options(
        session,
        days=int(days),
        limit=int(limit),
        source_type=source_type,
    )


@router.get("/events/{event_id}", response_model=OutboundReversalDetailOut)
async def get_outbound_reversal_detail_endpoint(
    event_id: int,
    session: AsyncSession = Depends(get_session),
) -> OutboundReversalDetailOut:
    return await get_outbound_reversal_detail(
        session,
        event_id=int(event_id),
    )


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
