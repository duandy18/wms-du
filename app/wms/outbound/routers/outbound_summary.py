# app/wms/outbound/routers/outbound_summary.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.user.deps.auth import get_current_user
from app.wms.outbound.contracts.outbound_summary import (
    OutboundSummaryDetailOut,
    OutboundSummaryLineOut,
    OutboundSummaryListOut,
    OutboundSummaryRowOut,
)
from app.wms.outbound.repos.outbound_summary_repo import (
    count_outbound_summary,
    get_outbound_summary_event,
    get_outbound_summary_lines,
    list_outbound_summary,
)

router = APIRouter(prefix="/wms/outbound", tags=["wms-outbound-summary"])


@router.get("/summary", response_model=OutboundSummaryListOut)
async def get_outbound_summary(
    source_type: str | None = None,
    warehouse_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> OutboundSummaryListOut:
    items = await list_outbound_summary(
        session,
        source_type=source_type,
        warehouse_id=warehouse_id,
        status=status,
        limit=int(limit),
        offset=int(offset),
    )
    total = await count_outbound_summary(
        session,
        source_type=source_type,
        warehouse_id=warehouse_id,
        status=status,
    )
    return OutboundSummaryListOut(
        items=[OutboundSummaryRowOut(**x) for x in items],
        total=int(total),
        limit=int(limit),
        offset=int(offset),
    )


@router.get("/summary/{event_id}", response_model=OutboundSummaryDetailOut)
async def get_outbound_summary_detail(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> OutboundSummaryDetailOut:
    event = await get_outbound_summary_event(session, event_id=int(event_id))
    lines = await get_outbound_summary_lines(session, event_id=int(event_id))
    return OutboundSummaryDetailOut(
        event=OutboundSummaryRowOut(**event),
        lines=[OutboundSummaryLineOut(**x) for x in lines],
    )
