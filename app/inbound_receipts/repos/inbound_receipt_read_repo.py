from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.inbound_receipts.contracts.receipt_read import (
    InboundReceiptLineReadOut,
    InboundReceiptListItemOut,
    InboundReceiptListOut,
    InboundReceiptProgressLineOut,
    InboundReceiptProgressOut,
    InboundReceiptReadOut,
)


async def list_inbound_receipts_repo(
    session: AsyncSession,
) -> InboundReceiptListOut:
    total = int(
        (
            await session.execute(
                text("SELECT COUNT(*) FROM inbound_receipts")
            )
        ).scalar_one()
    )

    rows = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  receipt_no,
                  source_type,
                  source_doc_no_snapshot,
                  warehouse_id,
                  warehouse_name_snapshot,
                  supplier_id,
                  counterparty_name_snapshot,
                  status,
                  remark,
                  released_at
                FROM inbound_receipts
                ORDER BY id DESC
                """
            )
        )
    ).mappings().all()

    return InboundReceiptListOut(
        total=total,
        items=[
            InboundReceiptListItemOut(
                id=int(r["id"]),
                receipt_no=str(r["receipt_no"]),
                source_type=str(r["source_type"]),
                source_doc_no_snapshot=r["source_doc_no_snapshot"],
                warehouse_id=int(r["warehouse_id"]),
                warehouse_name_snapshot=r["warehouse_name_snapshot"],
                supplier_id=r["supplier_id"],
                counterparty_name_snapshot=r["counterparty_name_snapshot"],
                status=str(r["status"]),
                remark=r["remark"],
                released_at=r["released_at"],
            )
            for r in rows
        ],
    )


async def get_inbound_receipt_repo(
    session: AsyncSession,
    *,
    receipt_id: int,
) -> InboundReceiptReadOut:
    header = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  receipt_no,
                  source_type,
                  source_doc_id,
                  source_doc_no_snapshot,
                  warehouse_id,
                  warehouse_name_snapshot,
                  supplier_id,
                  counterparty_name_snapshot,
                  status,
                  remark,
                  created_by,
                  released_at
                FROM inbound_receipts
                WHERE id = :receipt_id
                LIMIT 1
                """
            ),
            {"receipt_id": int(receipt_id)},
        )
    ).mappings().first()

    if header is None:
        raise HTTPException(status_code=404, detail="inbound_receipt_not_found")

    lines = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  line_no,
                  source_line_id,
                  item_id,
                  item_uom_id,
                  planned_qty,
                  item_name_snapshot,
                  item_spec_snapshot,
                  uom_name_snapshot,
                  ratio_to_base_snapshot,
                  remark
                FROM inbound_receipt_lines
                WHERE inbound_receipt_id = :receipt_id
                ORDER BY line_no ASC
                """
            ),
            {"receipt_id": int(receipt_id)},
        )
    ).mappings().all()

    return InboundReceiptReadOut(
        id=int(header["id"]),
        receipt_no=str(header["receipt_no"]),
        source_type=str(header["source_type"]),
        source_doc_id=header["source_doc_id"],
        source_doc_no_snapshot=header["source_doc_no_snapshot"],
        warehouse_id=int(header["warehouse_id"]),
        warehouse_name_snapshot=header["warehouse_name_snapshot"],
        supplier_id=header["supplier_id"],
        counterparty_name_snapshot=header["counterparty_name_snapshot"],
        status=str(header["status"]),
        remark=header["remark"],
        created_by=header["created_by"],
        released_at=header["released_at"],
        lines=[
            InboundReceiptLineReadOut(
                id=int(r["id"]),
                line_no=int(r["line_no"]),
                source_line_id=r["source_line_id"],
                item_id=int(r["item_id"]),
                item_uom_id=int(r["item_uom_id"]),
                planned_qty=r["planned_qty"],
                item_name_snapshot=r["item_name_snapshot"],
                item_spec_snapshot=r["item_spec_snapshot"],
                uom_name_snapshot=r["uom_name_snapshot"],
                ratio_to_base_snapshot=r["ratio_to_base_snapshot"],
                remark=r["remark"],
            )
            for r in lines
        ],
    )


async def get_inbound_receipt_progress_repo(
    session: AsyncSession,
    *,
    receipt_id: int,
) -> InboundReceiptProgressOut:
    header = (
        await session.execute(
            text(
                """
                SELECT id, receipt_no
                FROM inbound_receipts
                WHERE id = :receipt_id
                LIMIT 1
                """
            ),
            {"receipt_id": int(receipt_id)},
        )
    ).mappings().first()

    if header is None:
        raise HTTPException(status_code=404, detail="inbound_receipt_not_found")

    rows = (
        await session.execute(
            text(
                """
                SELECT
                  l.line_no,
                  l.planned_qty,
                  COALESCE(SUM(ol.qty_inbound), 0) AS received_qty,
                  GREATEST(l.planned_qty - COALESCE(SUM(ol.qty_inbound), 0), 0) AS remaining_qty
                FROM inbound_receipt_lines l
                LEFT JOIN wms_inbound_operations o
                  ON o.receipt_no_snapshot = :receipt_no
                LEFT JOIN wms_inbound_operation_lines ol
                  ON ol.wms_inbound_operation_id = o.id
                 AND ol.receipt_line_no_snapshot = l.line_no
                WHERE l.inbound_receipt_id = :receipt_id
                GROUP BY l.line_no, l.planned_qty
                ORDER BY l.line_no ASC
                """
            ),
            {
                "receipt_id": int(receipt_id),
                "receipt_no": str(header["receipt_no"]),
            },
        )
    ).mappings().all()

    return InboundReceiptProgressOut(
        receipt_id=int(header["id"]),
        receipt_no=str(header["receipt_no"]),
        lines=[
            InboundReceiptProgressLineOut(
                line_no=int(r["line_no"]),
                planned_qty=r["planned_qty"],
                received_qty=r["received_qty"],
                remaining_qty=r["remaining_qty"],
            )
            for r in rows
        ],
    )


__all__ = [
    "list_inbound_receipts_repo",
    "get_inbound_receipt_repo",
    "get_inbound_receipt_progress_repo",
]
