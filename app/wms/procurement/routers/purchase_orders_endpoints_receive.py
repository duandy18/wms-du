# app/wms/procurement/routers/purchase_orders_endpoints_receive.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
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
    stmt = select(PurchaseOrder.id, PurchaseOrder.status).where(PurchaseOrder.id == int(po_id))
    if for_update:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder not found: id={po_id}")
    st = str(row[1] or "").upper()
    if st != "CREATED":
        raise HTTPException(status_code=409, detail=f"PO 状态禁止执行收货：status={st}")


async def _resolve_uom_id_from_po_line_snapshot(
    session: AsyncSession,
    *,
    po_id: int,
    line_id: int | None,
    line_no: int | None,
) -> int:
    if line_id is None and line_no is None:
        raise HTTPException(status_code=400, detail="line_id 和 line_no 不能同时为空")

    if line_id is not None:
        row = (
            await session.execute(
                text(
                    """
                    SELECT purchase_uom_id_snapshot
                      FROM purchase_order_lines
                     WHERE id = :lid
                       AND po_id = :po_id
                     LIMIT 1
                    """
                ),
                {"lid": int(line_id), "po_id": int(po_id)},
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"PO line not found: line_id={int(line_id)}")
        return int(row)

    row = (
        await session.execute(
            text(
                """
                SELECT purchase_uom_id_snapshot
                  FROM purchase_order_lines
                 WHERE po_id = :po_id
                   AND line_no = :ln
                 LIMIT 1
                """
            ),
            {"po_id": int(po_id), "ln": int(line_no)},
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"PO line not found: line_no={int(line_no)}")
    return int(row)


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
            await _guard_po_created_for_execute(session, po_id=int(po_id), for_update=True)

            uom_id = payload.uom_id
            if uom_id is None:
                uom_id = await _resolve_uom_id_from_po_line_snapshot(
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
                batch_code=getattr(payload, "batch_code", None),
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
