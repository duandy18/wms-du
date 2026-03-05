# app/api/routers/purchase_orders_endpoints_core.py
"""
Purchase Orders Endpoints - Core（计划生命周期：create/get/close + receipts facts）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.purchase_order import PurchaseOrder
from app.schemas.purchase_order import (
    PurchaseOrderCloseIn,
    PurchaseOrderCreateV2,
    PurchaseOrderWithLinesOut,
)
from app.schemas.purchase_order_receipts import PurchaseOrderReceiptEventOut
from app.services.purchase_order_receipts import list_po_receipt_events
from app.services.purchase_order_service import PurchaseOrderService

UTC = timezone.utc


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    @router.post("/", response_model=PurchaseOrderWithLinesOut)
    async def create_purchase_order(
        payload: PurchaseOrderCreateV2,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderWithLinesOut:
        try:
            po = await svc.create_po_v2(
                session,
                supplier_id=payload.supplier_id,
                warehouse_id=payload.warehouse_id,
                purchaser=payload.purchaser,
                purchase_time=payload.purchase_time,
                remark=payload.remark,
                lines=[line.model_dump() for line in payload.lines],
            )
            await session.commit()
        except ValueError as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e)) from e

        po_out = await svc.get_po_with_lines(session, po.id)
        if po_out is None:
            raise HTTPException(status_code=500, detail="Failed to load created PurchaseOrder with lines")
        return po_out

    @router.get("/{po_id}", response_model=PurchaseOrderWithLinesOut)
    async def get_purchase_order(
        po_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderWithLinesOut:
        po_out = await svc.get_po_with_lines(session, po_id)
        if po_out is None:
            raise HTTPException(status_code=404, detail="PurchaseOrder not found")
        return po_out

    # ✅ 人工关闭采购计划（部分完成/终止剩余）
    @router.post("/{po_id}/close", response_model=PurchaseOrderWithLinesOut)
    async def close_purchase_order(
        po_id: int,
        payload: PurchaseOrderCloseIn,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderWithLinesOut:
        now = datetime.now(UTC)
        try:
            po = (
                (
                    await session.execute(
                        select(PurchaseOrder)
                        .options(selectinload(PurchaseOrder.lines))
                        .where(PurchaseOrder.id == int(po_id))
                        .with_for_update()
                    )
                )
                .scalars()
                .first()
            )
            if po is None:
                raise HTTPException(status_code=404, detail="PurchaseOrder not found")

            st = str(getattr(po, "status", "") or "").upper()
            if st != "CREATED":
                raise HTTPException(status_code=409, detail=f"PO 状态不允许关闭：status={st}")

            po.status = "CLOSED"
            po.closed_at = now
            po.close_reason = "MANUAL_TERMINATED"
            po.close_note = (payload.note or "").strip() or None
            # closed_by 预留：后续接 user_id
            await session.flush()
            await session.commit()

            po_out = await svc.get_po_with_lines(session, int(po_id))
            if po_out is None:
                raise HTTPException(status_code=500, detail="Failed to load closed PurchaseOrder with lines")
            return po_out
        except HTTPException:
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(e))

    # ✅ 采购单历史收货事实（读台账）
    @router.get("/{po_id}/receipts", response_model=List[PurchaseOrderReceiptEventOut])
    async def get_purchase_order_receipts(
        po_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> List[PurchaseOrderReceiptEventOut]:
        try:
            return await list_po_receipt_events(session, po_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
