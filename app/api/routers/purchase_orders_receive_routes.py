# app/api/routers/purchase_orders_receive_routes.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.inbound_receipt import InboundReceiptOut
from app.schemas.purchase_order_receive_workbench import PurchaseOrderReceiveWorkbenchOut
from app.services.inbound_receipt_query import get_receipt
from app.services.purchase_order_queries import get_po_with_lines
from app.services.purchase_order_receive import get_or_create_po_draft_receipt_explicit
from app.services.purchase_order_receive_workbench import get_receive_workbench
from app.services.purchase_order_time import UTC

# ✅ PO 收货工作台（独立 router，保持原路径不变）
po_receive_router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders-receive"])


@po_receive_router.post("/{po_id}/receipts/draft", response_model=InboundReceiptOut)
async def start_po_receive_draft(
    po_id: int,
    session: AsyncSession = Depends(get_session),
) -> InboundReceiptOut:
    """
    显式开始收货：创建/复用 PO 的 DRAFT receipt
    - 彻底消除“录入接口隐式生成 receipt”的行为
    """
    try:
        po = await get_po_with_lines(session, int(po_id), for_update=True)
        if po is None:
            raise HTTPException(status_code=404, detail=f"PurchaseOrder not found: id={po_id}")

        # ✅ 执行硬阻断：CLOSED / CANCELED 一律禁止开始收货
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
    """
    Workbench 统一输出：
    - po_summary（合同锚点）
    - receipt（当前 DRAFT 或 null）
    - rows（计划 + 已确认实收 + 草稿实收 + 剩余应收 + 批次维度）
    - explain（confirm 预检结果）
    - caps（可 confirm 与否）
    """
    try:
        out = await get_receive_workbench(session, po_id=int(po_id))
        return out
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
