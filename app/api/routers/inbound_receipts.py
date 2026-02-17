# app/api/routers/inbound_receipts.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.inbound_receipt import InboundReceiptOut
from app.services.inbound_receipt_query import get_receipt, list_receipts


router = APIRouter(prefix="/inbound-receipts", tags=["inbound-receipts"])


@router.get("/", response_model=List[InboundReceiptOut])
async def list_inbound_receipts(
    session: AsyncSession = Depends(get_session),
    ref: Optional[str] = Query(None),
    trace_id: Optional[str] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    source_type: Optional[str] = Query(None, description="PO / ORDER / OTHER"),
    source_id: Optional[int] = Query(None),
    time_from: Optional[datetime] = Query(None, description="occurred_at >= time_from"),
    time_to: Optional[datetime] = Query(None, description="occurred_at <= time_to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[InboundReceiptOut]:
    try:
        xs = await list_receipts(
            session,
            ref=ref,
            trace_id=trace_id,
            warehouse_id=warehouse_id,
            source_type=source_type,
            source_id=source_id,
            time_from=time_from,
            time_to=time_to,
            limit=limit,
            offset=offset,
        )
        return [InboundReceiptOut.model_validate(x) for x in xs]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{receipt_id}", response_model=InboundReceiptOut)
async def get_inbound_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptOut:
    try:
        obj = await get_receipt(session, receipt_id=receipt_id)
        return InboundReceiptOut.model_validate(obj)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
