# app/api/routers/purchase_orders_endpoints_receive.py
"""
Purchase Orders Endpoints - Receive（执行入口：receive-line + 执行硬阻断）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.purchase_order import PurchaseOrder
from app.schemas.purchase_order import PurchaseOrderReceiveLineIn
from app.schemas.purchase_order_receive_workbench import PurchaseOrderReceiveWorkbenchOut
from app.services.purchase_order_service import PurchaseOrderService


async def _guard_po_created_for_execute(
    session: AsyncSession,
    po_id: int,
    *,
    for_update: bool = True,
) -> None:
    """
    ✅ 执行硬阻断（Phase：计划生命周期封板 + 收货执行护栏）
    - status != CREATED -> 409
    - 这里用最小查询读取 status，并可选 for_update 锁 PO 行，避免 close/receive 并发漂移
    """
    stmt = select(PurchaseOrder.id, PurchaseOrder.status).where(PurchaseOrder.id == int(po_id))
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder not found: id={po_id}")
    st = str(row[1] or "").upper()
    if st != "CREATED":
        raise HTTPException(status_code=409, detail=f"PO 状态禁止执行收货：status={st}")


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    # ✅ Phase5+：收货录入后直接返回 workbench
    @router.post("/{po_id}/receive-line", response_model=PurchaseOrderReceiveWorkbenchOut)
    async def receive_purchase_order_line(
        po_id: int,
        payload: PurchaseOrderReceiveLineIn,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderReceiveWorkbenchOut:
        if payload.line_id is None and payload.line_no is None:
            raise HTTPException(status_code=400, detail="line_id 和 line_no 不能同时为空")

        try:
            # ✅ 执行硬阻断：CLOSED / CANCELED 一律禁止写入收货事实
            await _guard_po_created_for_execute(session, po_id=int(po_id), for_update=True)

            out = await svc.receive_po_line_workbench(
                session,
                po_id=po_id,
                line_id=payload.line_id,
                line_no=payload.line_no,
                qty=payload.qty,
                production_date=getattr(payload, "production_date", None),
                expiry_date=getattr(payload, "expiry_date", None),
                barcode=getattr(payload, "barcode", None),
            )
            await session.commit()
            return out
        except ValueError as e:
            await session.rollback()
            msg = str(e)
            if "请先开始收货" in msg or "未找到 PO 的 DRAFT 收货单" in msg:
                raise HTTPException(status_code=409, detail=msg) from e
            raise HTTPException(status_code=400, detail=msg) from e
        except HTTPException:
            await session.rollback()
            raise
