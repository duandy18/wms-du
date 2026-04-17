from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.inbound_receipts.contracts.receipt_create_from_purchase import (
    InboundReceiptCreateFromPurchaseIn,
    InboundReceiptCreateFromPurchaseOut,
)
from app.inbound_receipts.contracts.receipt_release import (
    InboundReceiptReleaseOut,
)
from app.inbound_receipts.repos.inbound_receipt_read_repo import (
    get_inbound_receipt_repo,
)

UTC = timezone.utc


def _new_receipt_no(po_id: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:6].upper()
    return f"IR-PO-{po_id}-{stamp}-{suffix}"


async def _load_warehouse_name_snapshot(
    session: AsyncSession,
    *,
    warehouse_id: int,
) -> str | None:
    has_name = bool(
        (
            await session.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.columns
                      WHERE table_schema = 'public'
                        AND table_name = 'warehouses'
                        AND column_name = 'name'
                    )
                    """
                )
            )
        ).scalar_one()
    )
    if has_name:
        return (
            await session.execute(
                text("SELECT name FROM warehouses WHERE id = :warehouse_id LIMIT 1"),
                {"warehouse_id": int(warehouse_id)},
            )
        ).scalar_one_or_none()

    has_code = bool(
        (
            await session.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.columns
                      WHERE table_schema = 'public'
                        AND table_name = 'warehouses'
                        AND column_name = 'code'
                    )
                    """
                )
            )
        ).scalar_one()
    )
    if has_code:
        return (
            await session.execute(
                text("SELECT code FROM warehouses WHERE id = :warehouse_id LIMIT 1"),
                {"warehouse_id": int(warehouse_id)},
            )
        ).scalar_one_or_none()

    return None


async def create_inbound_receipt_from_purchase_repo(
    session: AsyncSession,
    *,
    payload: InboundReceiptCreateFromPurchaseIn,
    created_by: int | None,
) -> InboundReceiptCreateFromPurchaseOut:
    po = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  po_no,
                  warehouse_id,
                  supplier_id,
                  supplier_name,
                  remark,
                  status
                FROM purchase_orders
                WHERE id = :po_id
                LIMIT 1
                """
            ),
            {"po_id": int(payload.source_doc_id)},
        )
    ).mappings().first()

    if po is None:
        raise HTTPException(status_code=404, detail="purchase_order_not_found")

    if str(po["status"]) != "CREATED":
        raise HTTPException(
            status_code=409,
            detail=f"purchase_order_not_creatable:{po['status']}",
        )

    if int(po["warehouse_id"]) != int(payload.warehouse_id):
        raise HTTPException(
            status_code=409,
            detail=(
                f"purchase_order_warehouse_mismatch:"
                f"po={po['warehouse_id']},payload={payload.warehouse_id}"
            ),
        )

    existing = (
        await session.execute(
            text(
                """
                SELECT id, receipt_no, status
                FROM inbound_receipts
                WHERE source_type = 'PURCHASE_ORDER'
                  AND source_doc_id = :po_id
                  AND status <> 'VOIDED'
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"po_id": int(payload.source_doc_id)},
        )
    ).mappings().first()

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"inbound_receipt_already_exists:{existing['receipt_no']}",
        )

    po_lines = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  line_no,
                  item_id,
                  item_name,
                  spec_text,
                  purchase_uom_id_snapshot,
                  purchase_ratio_to_base_snapshot,
                  qty_ordered_input,
                  purchase_uom_name_snapshot,
                  remark
                FROM purchase_order_lines
                WHERE po_id = :po_id
                ORDER BY line_no ASC
                """
            ),
            {"po_id": int(payload.source_doc_id)},
        )
    ).mappings().all()

    if not po_lines:
        raise HTTPException(status_code=409, detail="purchase_order_has_no_lines")

    receipt_no = _new_receipt_no(int(po["id"]))
    warehouse_name_snapshot = await _load_warehouse_name_snapshot(
        session,
        warehouse_id=int(payload.warehouse_id),
    )

    header = (
        await session.execute(
            text(
                """
                INSERT INTO inbound_receipts (
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
                )
                VALUES (
                  :receipt_no,
                  'PURCHASE_ORDER',
                  :source_doc_id,
                  :source_doc_no_snapshot,
                  :warehouse_id,
                  :warehouse_name_snapshot,
                  :supplier_id,
                  :counterparty_name_snapshot,
                  'DRAFT',
                  :remark,
                  :created_by,
                  NULL
                )
                RETURNING id
                """
            ),
            {
                "receipt_no": receipt_no,
                "source_doc_id": int(po["id"]),
                "source_doc_no_snapshot": po["po_no"],
                "warehouse_id": int(payload.warehouse_id),
                "warehouse_name_snapshot": warehouse_name_snapshot,
                "supplier_id": po["supplier_id"],
                "counterparty_name_snapshot": po["supplier_name"],
                "remark": payload.remark if payload.remark is not None else po["remark"],
                "created_by": created_by,
            },
        )
    ).mappings().first()

    receipt_id = int(header["id"])

    for row in po_lines:
        await session.execute(
            text(
                """
                INSERT INTO inbound_receipt_lines (
                  inbound_receipt_id,
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
                )
                VALUES (
                  :inbound_receipt_id,
                  :line_no,
                  :source_line_id,
                  :item_id,
                  :item_uom_id,
                  :planned_qty,
                  :item_name_snapshot,
                  :item_spec_snapshot,
                  :uom_name_snapshot,
                  :ratio_to_base_snapshot,
                  :remark
                )
                """
            ),
            {
                "inbound_receipt_id": receipt_id,
                "line_no": int(row["line_no"]),
                "source_line_id": int(row["id"]),
                "item_id": int(row["item_id"]),
                "item_uom_id": int(row["purchase_uom_id_snapshot"]),
                "planned_qty": row["qty_ordered_input"],
                "item_name_snapshot": row["item_name"],
                "item_spec_snapshot": row["spec_text"],
                "uom_name_snapshot": row["purchase_uom_name_snapshot"],
                "ratio_to_base_snapshot": row["purchase_ratio_to_base_snapshot"],
                "remark": row["remark"],
            },
        )

    return await get_inbound_receipt_repo(session, receipt_id=receipt_id)


async def release_inbound_receipt_repo(
    session: AsyncSession,
    *,
    receipt_id: int,
) -> InboundReceiptReleaseOut:
    row = (
        await session.execute(
            text(
                """
                UPDATE inbound_receipts
                SET
                  status = 'RELEASED',
                  released_at = COALESCE(released_at, now())
                WHERE id = :receipt_id
                  AND status = 'DRAFT'
                RETURNING
                  id AS receipt_id,
                  receipt_no,
                  status,
                  released_at
                """
            ),
            {"receipt_id": int(receipt_id)},
        )
    ).mappings().first()

    if row is not None:
        return InboundReceiptReleaseOut(
            receipt_id=int(row["receipt_id"]),
            receipt_no=str(row["receipt_no"]),
            status="RELEASED",
            released_at=row["released_at"],
        )

    existing = (
        await session.execute(
            text(
                """
                SELECT id, receipt_no, status, released_at
                FROM inbound_receipts
                WHERE id = :receipt_id
                LIMIT 1
                """
            ),
            {"receipt_id": int(receipt_id)},
        )
    ).mappings().first()

    if existing is None:
        raise HTTPException(status_code=404, detail="inbound_receipt_not_found")

    if str(existing["status"]) == "RELEASED":
        return InboundReceiptReleaseOut(
            receipt_id=int(existing["id"]),
            receipt_no=str(existing["receipt_no"]),
            status="RELEASED",
            released_at=existing["released_at"],
        )

    raise HTTPException(
        status_code=409,
        detail=f"inbound_receipt_not_releasable:{existing['status']}",
    )


__all__ = [
    "create_inbound_receipt_from_purchase_repo",
    "release_inbound_receipt_repo",
]
