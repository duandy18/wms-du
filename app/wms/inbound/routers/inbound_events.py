# app/wms/inbound/routers/inbound_events.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.inbound.contracts.inbound_event_read import (
    InboundEventDetailOut,
    InboundEventListOut,
)
from app.wms.inbound.services.inbound_event_read_service import (
    get_inbound_event_detail,
    list_inbound_events,
)

router = APIRouter(prefix="/wms/inbound", tags=["wms-inbound-events"])


@router.get("/events", response_model=InboundEventListOut)
async def list_inbound_events_endpoint(
    warehouse_id: int | None = Query(default=None, ge=1, description="仓库 ID"),
    source_type: str | None = Query(default=None, description="来源类型"),
    source_ref: str | None = Query(default=None, description="来源单号/外部引用号"),
    date_from: datetime | None = Query(default=None, description="业务发生时间起点（含）"),
    date_to: datetime | None = Query(default=None, description="业务发生时间终点（含）"),
    limit: int = Query(default=20, ge=1, le=200, description="分页大小"),
    offset: int = Query(default=0, ge=0, description="分页偏移"),
    session: AsyncSession = Depends(get_session),
) -> InboundEventListOut:
    try:
        return await list_inbound_events(
            session,
            warehouse_id=warehouse_id,
            source_type=source_type,
            source_ref=source_ref,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/events/{event_id}", response_model=InboundEventDetailOut)
async def get_inbound_event_detail_endpoint(
    event_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundEventDetailOut:
    try:
        return await get_inbound_event_detail(
            session,
            event_id=int(event_id),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


__all__ = ["router"]
