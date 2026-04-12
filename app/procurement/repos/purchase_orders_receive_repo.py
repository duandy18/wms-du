from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.models.purchase_order import PurchaseOrder


async def guard_po_created_for_execute(
    session: AsyncSession,
    *,
    po_id: int,
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


async def resolve_uom_id_from_po_line_snapshot(
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


__all__ = [
    "guard_po_created_for_execute",
    "resolve_uom_id_from_po_line_snapshot",
]
