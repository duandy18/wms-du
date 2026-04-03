# app/wms/procurement/routers/purchase_orders_receive.py
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.procurement.contracts.inbound_receipt import InboundReceiptOut
from app.wms.procurement.contracts.purchase_order_receive_workbench import PurchaseOrderReceiveWorkbenchOut
from app.wms.procurement.services.inbound_receipt_query import get_receipt
from app.wms.procurement.repos.purchase_order_queries_repo import get_po_with_lines
from app.wms.procurement.repos.receipt_draft_repo import get_or_create_po_draft_receipt_explicit
from app.wms.procurement.services.purchase_order_receive_workbench import get_receive_workbench
UTC = timezone.utc

po_receive_router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders-receive"])


@po_receive_router.post("/{po_id}/receipts/draft", response_model=InboundReceiptOut)
async def start_po_receive_draft(
    po_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptOut:
    try:
        po = await get_po_with_lines(session, int(po_id), for_update=True)
        if po is None:
            raise HTTPException(status_code=404, detail=f"PurchaseOrder not found: id={po_id}")

        st = str(getattr(po, "status", "") or "").upper()
        if st != "CREATED":
            raise HTTPException(status_code=409, detail=f"PO 状态禁止执行收货：status={st}")

        now = datetime.now(UTC)
        draft = await get_or_create_po_draft_receipt_explicit(session, po=po, occurred_at=now)

        await session.flush()
        loaded = await get_receipt(session, receipt_id=int(draft.id))

        await session.commit()
        return InboundReceiptOut.model_validate(loaded)
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@po_receive_router.get("/{po_id}/receive-workbench", response_model=PurchaseOrderReceiveWorkbenchOut)
async def get_po_receive_workbench(
    po_id: int,
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderReceiveWorkbenchOut:
    try:
        out = await get_receive_workbench(session, po_id=int(po_id))
        return out
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
