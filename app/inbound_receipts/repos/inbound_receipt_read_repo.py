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
from app.inbound_receipts.contracts.receipt_return_source import (
    InboundReceiptReturnSourceLineOut,
    InboundReceiptReturnSourceOut,
)
from app.oms.services.order_ref_resolver import resolve_order_id


RETURN_SHIP_REASONS = ("SHIPMENT", "OUTBOUND_SHIP")


async def _resolve_order_identity(
    session: AsyncSession,
    *,
    order_key: str,
) -> dict[str, object]:
    order_id = int(await resolve_order_id(session, order_ref=order_key))
    row = (
        await session.execute(
            text(
                """
                SELECT id, platform, shop_id, ext_order_no
                FROM orders
                WHERE id = :order_id
                LIMIT 1
                """
            ),
            {"order_id": order_id},
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="return_order_not_found")

    platform = str(row["platform"])
    shop_id = str(row["shop_id"])
    ext_order_no = str(row["ext_order_no"])
    return {
        "order_id": int(row["id"]),
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
        "order_ref": f"ORD:{platform}:{shop_id}:{ext_order_no}",
    }


async def _load_return_source_warehouse(
    session: AsyncSession,
    *,
    order_ref: str,
) -> tuple[int, str | None]:
    wh_rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT warehouse_id
                FROM stock_ledger
                WHERE ref = :ref
                  AND delta < 0
                  AND reason = ANY(:reasons)
                ORDER BY warehouse_id ASC
                LIMIT 2
                """
            ),
            {"ref": str(order_ref), "reasons": list(RETURN_SHIP_REASONS)},
        )
    ).mappings().all()

    if not wh_rows:
        raise HTTPException(status_code=409, detail="return_order_has_no_shipped_facts")

    if len(wh_rows) > 1:
        ids = ",".join(str(int(x["warehouse_id"])) for x in wh_rows)
        raise HTTPException(status_code=409, detail=f"return_order_multi_warehouse:{ids}")

    warehouse_id = int(wh_rows[0]["warehouse_id"])
    warehouse_name = (
        await session.execute(
            text("SELECT name FROM warehouses WHERE id = :warehouse_id LIMIT 1"),
            {"warehouse_id": warehouse_id},
        )
    ).scalar_one_or_none()
    return warehouse_id, warehouse_name


async def get_inbound_return_source_repo(
    session: AsyncSession,
    *,
    order_key: str,
) -> InboundReceiptReturnSourceOut:
    ident = await _resolve_order_identity(session, order_key=order_key)
    order_id = int(ident["order_id"])
    order_ref = str(ident["order_ref"])
    warehouse_id, warehouse_name_snapshot = await _load_return_source_warehouse(
        session,
        order_ref=order_ref,
    )

    line_rows = (
        await session.execute(
            text(
                """
                SELECT
                  oi.id AS order_line_id,
                  oi.item_id AS item_id,
                  COALESCE(i.name, oi.title) AS item_name_snapshot,
                  i.spec AS item_spec_snapshot,
                  (
                    SELECT u.id
                    FROM item_uoms u
                    WHERE u.item_id = oi.item_id
                    ORDER BY
                      CASE WHEN u.is_inbound_default THEN 0 WHEN u.is_base THEN 1 ELSE 2 END,
                      u.id
                    LIMIT 1
                  ) AS item_uom_id,
                  (
                    SELECT COALESCE(NULLIF(u.display_name, ''), u.uom)
                    FROM item_uoms u
                    WHERE u.item_id = oi.item_id
                    ORDER BY
                      CASE WHEN u.is_inbound_default THEN 0 WHEN u.is_base THEN 1 ELSE 2 END,
                      u.id
                    LIMIT 1
                  ) AS uom_name_snapshot,
                  (
                    SELECT u.ratio_to_base::numeric
                    FROM item_uoms u
                    WHERE u.item_id = oi.item_id
                    ORDER BY
                      CASE WHEN u.is_inbound_default THEN 0 WHEN u.is_base THEN 1 ELSE 2 END,
                      u.id
                    LIMIT 1
                  ) AS ratio_to_base_snapshot,
                  COALESCE(oi.qty, 0)::numeric AS qty_ordered,
                  COALESCE(oi.shipped_qty, 0)::numeric AS qty_shipped,
                  COALESCE(oi.returned_qty, 0)::numeric AS qty_returned,
                  GREATEST(COALESCE(oi.shipped_qty, 0) - COALESCE(oi.returned_qty, 0), 0)::numeric AS qty_remaining_refundable
                FROM order_items oi
                LEFT JOIN items i ON i.id = oi.item_id
                WHERE oi.order_id = :order_id
                  AND GREATEST(COALESCE(oi.shipped_qty, 0) - COALESCE(oi.returned_qty, 0), 0) > 0
                ORDER BY oi.id ASC
                """
            ),
            {"order_id": order_id},
        )
    ).mappings().all()

    if not line_rows:
        raise HTTPException(status_code=409, detail="return_order_has_no_refundable_lines")

    lines: list[InboundReceiptReturnSourceLineOut] = []
    remaining_qty = 0

    for row in line_rows:
        item_id = int(row["item_id"])
        item_uom_id = int(row["item_uom_id"] or 0)
        if item_uom_id <= 0:
            raise HTTPException(status_code=409, detail=f"item_has_no_inbound_uom:item_id={item_id}")

        line = InboundReceiptReturnSourceLineOut(
            order_line_id=int(row["order_line_id"]),
            item_id=item_id,
            item_name_snapshot=row["item_name_snapshot"],
            item_spec_snapshot=row["item_spec_snapshot"],
            item_uom_id=item_uom_id,
            uom_name_snapshot=row["uom_name_snapshot"],
            ratio_to_base_snapshot=row["ratio_to_base_snapshot"] or 1,
            qty_ordered=row["qty_ordered"] or 0,
            qty_shipped=row["qty_shipped"] or 0,
            qty_returned=row["qty_returned"] or 0,
            qty_remaining_refundable=row["qty_remaining_refundable"] or 0,
            suggested_planned_qty=row["qty_remaining_refundable"] or 0,
        )
        lines.append(line)
        remaining_qty += int(row["qty_remaining_refundable"] or 0)

    existing = (
        await session.execute(
            text(
                """
                SELECT id, receipt_no, status
                FROM inbound_receipts
                WHERE source_type = 'RETURN_ORDER'
                  AND source_doc_id = :order_id
                  AND status <> 'VOIDED'
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"order_id": order_id},
        )
    ).mappings().first()

    return InboundReceiptReturnSourceOut(
        order_id=order_id,
        order_ref=order_ref,
        platform=str(ident["platform"]),
        shop_id=str(ident["shop_id"]),
        ext_order_no=str(ident["ext_order_no"]),
        warehouse_id=warehouse_id,
        warehouse_name_snapshot=warehouse_name_snapshot,
        remaining_qty=remaining_qty,
        existing_receipt_id=int(existing["id"]) if existing is not None else None,
        existing_receipt_no=str(existing["receipt_no"]) if existing is not None else None,
        existing_receipt_status=str(existing["status"]) if existing is not None else None,
        lines=lines,
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
                  COALESCE(
                    SUM(COALESCE(ol.qty_base, 0)::numeric / NULLIF(l.ratio_to_base_snapshot, 0)::numeric),
                    0
                  ) AS received_qty,
                  COALESCE(
                    GREATEST(
                      (l.planned_qty * l.ratio_to_base_snapshot) - COALESCE(SUM(ol.qty_base), 0),
                      0
                    )::numeric / NULLIF(l.ratio_to_base_snapshot, 0)::numeric,
                    0
                  ) AS remaining_qty
                FROM inbound_receipt_lines l
                LEFT JOIN wms_inbound_operations o
                  ON o.receipt_no_snapshot = :receipt_no
                LEFT JOIN wms_inbound_operation_lines ol
                  ON ol.wms_inbound_operation_id = o.id
                 AND ol.receipt_line_no_snapshot = l.line_no
                WHERE l.inbound_receipt_id = :receipt_id
                GROUP BY l.line_no, l.planned_qty, l.ratio_to_base_snapshot
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
    "get_inbound_return_source_repo",
]
