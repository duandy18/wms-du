from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inbound_operations.contracts.inbound_task_read import (
    InboundTaskLineOut,
    InboundTaskReadOut,
)


async def get_inbound_task_repo(
    session: AsyncSession,
    *,
    receipt_no: str,
) -> InboundTaskReadOut:
    header = (
        await session.execute(
            text(
                """
                SELECT
                  id AS receipt_id,
                  receipt_no,
                  source_type,
                  source_doc_no_snapshot,
                  warehouse_id,
                  warehouse_name_snapshot,
                  supplier_id,
                  counterparty_name_snapshot,
                  status,
                  remark
                FROM inbound_receipts
                WHERE receipt_no = :receipt_no
                LIMIT 1
                """
            ),
            {"receipt_no": str(receipt_no)},
        )
    ).mappings().first()

    if header is None:
        raise HTTPException(status_code=404, detail="inbound_task_not_found")

    if str(header["status"]) != "RELEASED":
        raise HTTPException(
            status_code=409,
            detail=f"inbound_task_not_released:{header['status']}",
        )

    rows = (
        await session.execute(
            text(
                """
                SELECT
                  l.line_no,
                  l.item_id,
                  l.item_uom_id,
                  l.planned_qty,
                  l.item_name_snapshot,
                  l.item_spec_snapshot,
                  l.uom_name_snapshot,
                  l.ratio_to_base_snapshot,
                  COALESCE(SUM(ol.qty_inbound), 0) AS received_qty,
                  GREATEST(l.planned_qty - COALESCE(SUM(ol.qty_inbound), 0), 0) AS remaining_qty,
                  l.remark
                FROM inbound_receipt_lines l
                LEFT JOIN wms_inbound_operations o
                  ON o.receipt_no_snapshot = :receipt_no
                LEFT JOIN wms_inbound_operation_lines ol
                  ON ol.wms_inbound_operation_id = o.id
                 AND ol.receipt_line_no_snapshot = l.line_no
                WHERE l.inbound_receipt_id = :receipt_id
                GROUP BY
                  l.line_no,
                  l.item_id,
                  l.item_uom_id,
                  l.planned_qty,
                  l.item_name_snapshot,
                  l.item_spec_snapshot,
                  l.uom_name_snapshot,
                  l.ratio_to_base_snapshot,
                  l.remark
                ORDER BY l.line_no ASC
                """
            ),
            {
                "receipt_no": str(receipt_no),
                "receipt_id": int(header["receipt_id"]),
            },
        )
    ).mappings().all()

    return InboundTaskReadOut(
        receipt_id=int(header["receipt_id"]),
        receipt_no=str(header["receipt_no"]),
        source_type=str(header["source_type"]),
        source_doc_no_snapshot=header["source_doc_no_snapshot"],
        warehouse_id=int(header["warehouse_id"]),
        warehouse_name_snapshot=header["warehouse_name_snapshot"],
        supplier_id=header["supplier_id"],
        counterparty_name_snapshot=header["counterparty_name_snapshot"],
        status=str(header["status"]),
        remark=header["remark"],
        lines=[
            InboundTaskLineOut(
                line_no=int(r["line_no"]),
                item_id=int(r["item_id"]),
                item_uom_id=int(r["item_uom_id"]),
                planned_qty=r["planned_qty"],
                item_name_snapshot=r["item_name_snapshot"],
                item_spec_snapshot=r["item_spec_snapshot"],
                uom_name_snapshot=r["uom_name_snapshot"],
                ratio_to_base_snapshot=r["ratio_to_base_snapshot"],
                received_qty=r["received_qty"],
                remaining_qty=r["remaining_qty"],
                remark=r["remark"],
            )
            for r in rows
        ],
    )


__all__ = [
    "get_inbound_task_repo",
]
