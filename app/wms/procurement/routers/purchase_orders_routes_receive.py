# app/wms/procurement/routers/purchase_orders_routes_receive.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.procurement.contracts.purchase_order import PurchaseOrderReceiveLineIn
from app.wms.procurement.contracts.purchase_order_receive_workbench import PurchaseOrderReceiveWorkbenchOut
from app.wms.procurement.repos.purchase_orders_receive_repo import (
    guard_po_created_for_execute,
    resolve_uom_id_from_po_line_snapshot,
)
from app.wms.procurement.services.purchase_order_service import PurchaseOrderService


def register(router: APIRouter, svc: PurchaseOrderService) -> None:
    @router.post("/{po_id}/receive-line", response_model=PurchaseOrderReceiveWorkbenchOut)
    async def receive_purchase_order_line(
        po_id: int,
        payload: PurchaseOrderReceiveLineIn,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderReceiveWorkbenchOut:
        if payload.line_id is None and payload.line_no is None:
            raise HTTPException(status_code=400, detail="line_id 和 line_no 不能同时为空")

        try:
            await guard_po_created_for_execute(session, po_id=int(po_id), for_update=True)

            uom_id = payload.uom_id
            if uom_id is None:
                uom_id = await resolve_uom_id_from_po_line_snapshot(
                    session,
                    po_id=int(po_id),
                    line_id=payload.line_id,
                    line_no=payload.line_no,
                )

            out = await svc.receive_po_line_workbench(
                session,
                po_id=po_id,
                line_id=payload.line_id,
                line_no=payload.line_no,
                uom_id=int(uom_id),
                qty=payload.qty,
                lot_code=getattr(payload, "lot_code", None),
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
