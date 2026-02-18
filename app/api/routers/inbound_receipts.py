# app/api/routers/inbound_receipts.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.inbound_receipt import InboundReceiptOut
from app.schemas.inbound_receipt_confirm import InboundReceiptConfirmOut
from app.schemas.inbound_receipt_explain import InboundReceiptExplainOut
from app.services.inbound_receipt_confirm import confirm_receipt
from app.services.inbound_receipt_explain import explain_receipt
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


@router.get("/{receipt_id}/explain", response_model=InboundReceiptExplainOut)
async def explain_inbound_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptExplainOut:
    """
    Preflight explain（确认前预检）：
    - 只读 Receipt 事实层（InboundReceipt / InboundReceiptLine）
    - 不写库
    """
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
    """
    Phase5：Receipt confirm（唯一库存写入口）
    - 必须 commit：CONFIRMED 是事实固化；库存流水是结果固化
    """
    try:
        out = await confirm_receipt(session=session, receipt_id=int(receipt_id), user_id=None)
        await session.commit()
        return out
    except HTTPException:
        # Problem 化异常必须原样透传，但也必须 rollback，避免事务脏掉
        await session.rollback()
        raise
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
