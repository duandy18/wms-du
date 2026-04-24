from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.inventory_adjustment.inbound_reversal.contracts.inbound_reversal import (
    InboundReversalIn,
    InboundReversalOut,
)
from app.wms.inventory_adjustment.inbound_reversal.contracts.inbound_reversal_read import (
    InboundReversalDetailOut,
    InboundReversalOptionsOut,
)
from app.wms.inventory_adjustment.inbound_reversal.services.inbound_reversal_service import (
    get_reversible_inbound_event_detail,
    list_reversible_inbound_events,
    reverse_inbound_event,
)

router = APIRouter(
    prefix="/inventory-adjustment/inbound-reversal",
    tags=["inventory-adjustment-inbound-reversal"],
)


@router.get("/options", response_model=InboundReversalOptionsOut)
async def list_inbound_reversal_options_endpoint(
    days: int = Query(default=7, ge=1, le=30, description="候选事件时间段，单位天"),
    limit: int = Query(default=50, ge=1, le=100, description="返回条数上限"),
    source_type: str | None = Query(default=None, description="可选来源类型过滤"),
    session: AsyncSession = Depends(get_session),
) -> InboundReversalOptionsOut:
    return await list_reversible_inbound_events(
        session,
        days=days,
        limit=limit,
        source_type=source_type,
    )


@router.get("/events/{event_id}", response_model=InboundReversalDetailOut)
async def get_inbound_reversal_detail_endpoint(
    event_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReversalDetailOut:
    return await get_reversible_inbound_event_detail(
        session,
        event_id=int(event_id),
    )


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
