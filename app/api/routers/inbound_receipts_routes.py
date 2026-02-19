# app/api/routers/inbound_receipts_routes.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.inbound_receipt import InboundReceiptOut
from app.schemas.inbound_receipt_confirm import InboundReceiptConfirmOut
from app.schemas.inbound_receipt_create import InboundReceiptCreateIn
from app.schemas.inbound_receipt_explain import InboundReceiptExplainOut
from app.services.inbound_receipt_confirm import confirm_receipt
from app.services.inbound_receipt_create import create_po_draft_receipt
from app.services.inbound_receipt_explain import explain_receipt
from app.services.inbound_receipt_query import get_receipt, list_receipts

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
    """
    Phase5：Receipt 创建入口（DRAFT）
    - 当前仅支持 PO：创建/复用最新 DRAFT receipt
    - ✅ 只写 Receipt(DRAFT) 事实
    - ❌ 不写库存（库存只能由 /confirm 触发）

    重要：返回前必须确保 lines 已加载，避免 async 环境下触发 relationship lazyload -> MissingGreenlet
    """
    try:
        st = _norm_source_type(payload.source_type)
        if st != "PO":
            raise HTTPException(status_code=400, detail=f"unsupported source_type: {payload.source_type}")

        obj = await create_po_draft_receipt(
            session,
            po_id=int(payload.source_id),
            occurred_at=payload.occurred_at,
        )

        # ✅ 关键：用 query 再读一次（selectinload lines），避免 Pydantic 访问 obj.lines 触发 MissingGreenlet
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
