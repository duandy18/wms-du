# app/wms/procurement/routers/inbound_receipts_routes.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.procurement.contracts.inbound_receipt import InboundReceiptOut
from app.procurement.contracts.inbound_receipt_confirm import InboundReceiptConfirmOut
from app.procurement.contracts.inbound_receipt_create import InboundReceiptCreateIn
from app.procurement.contracts.inbound_receipt_explain import InboundReceiptExplainOut
from app.procurement.services.inbound_receipt_confirm import confirm_receipt
from app.procurement.services.inbound_receipt_create import create_po_draft_receipt
from app.procurement.services.inbound_receipt_explain import explain_receipt
from app.procurement.services.inbound_receipt_query import get_receipt, list_receipts

router = APIRouter(prefix="/inbound-receipts", tags=["inbound-receipts"])


def _norm_source_type(raw: str) -> str:
    v = str(raw or "").strip().upper()
    if v in {"PURCHASE_ORDER", "PURCHASE-ORDER", "PURCHASEORDER"}:
        return "PO"
    return v


@router.post("/", response_model=InboundReceiptOut)
async def create_inbound_receipt(
    payload: InboundReceiptCreateIn,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptOut:
    try:
        st = _norm_source_type(payload.source_type)
        if st != "PO":
            raise HTTPException(status_code=400, detail=f"unsupported source_type: {payload.source_type}")

        obj = await create_po_draft_receipt(
            session,
            po_id=int(payload.source_id),
            occurred_at=payload.occurred_at,
        )

        await session.flush()
        loaded = await get_receipt(session, receipt_id=int(obj.id))

        await session.commit()
        return InboundReceiptOut.model_validate(loaded)
    except HTTPException:
        await session.rollback()
        raise
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


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


@router.get("/{receipt_id}/explain", response_model=InboundReceiptExplainOut)
async def explain_inbound_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptExplainOut:
    try:
        obj = await get_receipt(session, receipt_id=receipt_id)
        return await explain_receipt(session=session, receipt=obj)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{receipt_id}/confirm", response_model=InboundReceiptConfirmOut)
async def confirm_inbound_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptConfirmOut:
    try:
        out = await confirm_receipt(session=session, receipt_id=int(receipt_id), user_id=None)
        await session.commit()
        return out
    except HTTPException:
        await session.rollback()
        raise
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
