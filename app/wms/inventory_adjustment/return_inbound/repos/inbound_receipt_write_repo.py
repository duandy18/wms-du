from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inventory_adjustment.return_inbound.contracts.receipt_create_from_purchase import (
    InboundReceiptCreateFromPurchaseIn,
    InboundReceiptCreateFromPurchaseOut,
)
from app.wms.inventory_adjustment.return_inbound.contracts.receipt_create_manual import (
    InboundReceiptCreateManualIn,
    InboundReceiptCreateManualOut,
)
from app.wms.inventory_adjustment.return_inbound.contracts.receipt_create_from_return_order import (
    InboundReceiptCreateFromReturnOrderIn,
    InboundReceiptCreateFromReturnOrderOut,
)
from app.wms.inventory_adjustment.return_inbound.contracts.receipt_release import (
    InboundReceiptReleaseOut,
)
from app.wms.inventory_adjustment.return_inbound.repos.inbound_receipt_read_repo import (
    get_inbound_receipt_repo,
    get_inbound_return_source_repo,
)

UTC = timezone.utc


def _new_receipt_no(po_id: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:6].upper()
    return f"IR-PO-{po_id}-{stamp}-{suffix}"


def _new_manual_receipt_no() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:6].upper()
    return f"IR-MA-{stamp}-{suffix}"


def _new_return_receipt_no(order_id: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:6].upper()
    return f"IR-RO-{order_id}-{stamp}-{suffix}"


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


async def _load_supplier_name_snapshot(
    session: AsyncSession,
    *,
    supplier_id: int,
) -> str:
    row = (
        await session.execute(
            text("SELECT name FROM suppliers WHERE id = :supplier_id LIMIT 1"),
            {"supplier_id": int(supplier_id)},
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="supplier_not_found")
    return str(row)


async def _load_manual_line_snapshot(
    session: AsyncSession,
    *,
    item_id: int,
    item_uom_id: int,
) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  i.id AS item_id,
                  i.name AS item_name,
                  i.spec AS item_spec,
                  u.id AS item_uom_id,
                  COALESCE(NULLIF(u.display_name, ''), u.uom) AS uom_name,
                  u.ratio_to_base AS ratio_to_base
                FROM items i
                JOIN item_uoms u
                  ON u.item_id = i.id
                WHERE i.id = :item_id
                  AND u.id = :item_uom_id
                LIMIT 1
                """
            ),
            {
                "item_id": int(item_id),
                "item_uom_id": int(item_uom_id),
            },
        )
    ).mappings().first()

    if row is not None:
        return dict(row)

    item_exists = (
        await session.execute(
            text("SELECT 1 FROM items WHERE id = :item_id LIMIT 1"),
            {"item_id": int(item_id)},
        )
    ).scalar_one_or_none()
    if item_exists is None:
        raise HTTPException(status_code=404, detail="item_not_found")

    uom_exists = (
        await session.execute(
            text("SELECT 1 FROM item_uoms WHERE id = :item_uom_id LIMIT 1"),
            {"item_uom_id": int(item_uom_id)},
        )
    ).scalar_one_or_none()
    if uom_exists is None:
        raise HTTPException(status_code=404, detail="item_uom_not_found")

    raise HTTPException(
        status_code=409,
        detail=f"item_uom_item_mismatch:item_id={int(item_id)},item_uom_id={int(item_uom_id)}",
    )


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


async def create_inbound_receipt_manual_repo(
    session: AsyncSession,
    *,
    payload: InboundReceiptCreateManualIn,
    created_by: int | None,
) -> InboundReceiptCreateManualOut:
    warehouse_exists = (
        await session.execute(
            text("SELECT 1 FROM warehouses WHERE id = :warehouse_id LIMIT 1"),
            {"warehouse_id": int(payload.warehouse_id)},
        )
    ).scalar_one_or_none()
    if warehouse_exists is None:
        raise HTTPException(status_code=404, detail="warehouse_not_found")

    warehouse_name_snapshot = await _load_warehouse_name_snapshot(
        session,
        warehouse_id=int(payload.warehouse_id),
    )

    supplier_name_snapshot: str | None = None
    if payload.supplier_id is not None:
        supplier_name_snapshot = await _load_supplier_name_snapshot(
            session,
            supplier_id=int(payload.supplier_id),
        )

    receipt_no = _new_manual_receipt_no()

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
                  'MANUAL',
                  NULL,
                  NULL,
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
                "warehouse_id": int(payload.warehouse_id),
                "warehouse_name_snapshot": warehouse_name_snapshot,
                "supplier_id": int(payload.supplier_id) if payload.supplier_id is not None else None,
                "counterparty_name_snapshot": supplier_name_snapshot,
                "remark": payload.remark,
                "created_by": created_by,
            },
        )
    ).mappings().first()

    receipt_id = int(header["id"])

    for idx, line in enumerate(payload.lines, start=1):
        snap = await _load_manual_line_snapshot(
            session,
            item_id=int(line.item_id),
            item_uom_id=int(line.item_uom_id),
        )

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
                  NULL,
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
                "line_no": idx,
                "item_id": int(line.item_id),
                "item_uom_id": int(line.item_uom_id),
                "planned_qty": line.planned_qty,
                "item_name_snapshot": snap["item_name"],
                "item_spec_snapshot": snap["item_spec"],
                "uom_name_snapshot": snap["uom_name"],
                "ratio_to_base_snapshot": snap["ratio_to_base"],
                "remark": line.remark,
            },
        )

    return await get_inbound_receipt_repo(session, receipt_id=receipt_id)


async def create_inbound_receipt_from_return_order_repo(
    session: AsyncSession,
    *,
    payload: InboundReceiptCreateFromReturnOrderIn,
    created_by: int | None,
) -> InboundReceiptCreateFromReturnOrderOut:
    source = await get_inbound_return_source_repo(session, order_key=payload.order_key)

    if source.existing_receipt_id is not None and source.existing_receipt_no is not None:
        raise HTTPException(
            status_code=409,
            detail=f"inbound_receipt_already_exists:{source.existing_receipt_no}",
        )

    if not source.lines:
        raise HTTPException(status_code=409, detail="return_order_has_no_refundable_lines")

    counterparty_name_snapshot = None
    if source.platform and source.store_code:
        counterparty_name_snapshot = f"{source.platform}:{source.store_code}"
    elif source.platform:
        counterparty_name_snapshot = source.platform
    elif source.store_code:
        counterparty_name_snapshot = source.store_code

    receipt_no = _new_return_receipt_no(int(source.order_id))

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
                  'RETURN_ORDER',
                  :source_doc_id,
                  :source_doc_no_snapshot,
                  :warehouse_id,
                  :warehouse_name_snapshot,
                  NULL,
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
                "source_doc_id": int(source.order_id),
                "source_doc_no_snapshot": source.ext_order_no or source.order_ref,
                "warehouse_id": int(source.warehouse_id),
                "warehouse_name_snapshot": source.warehouse_name_snapshot,
                "counterparty_name_snapshot": counterparty_name_snapshot,
                "remark": payload.remark,
                "created_by": created_by,
            },
        )
    ).mappings().first()

    receipt_id = int(header["id"])
    source_map = {int(line.order_line_id): line for line in source.lines}
    seen_order_line_ids: set[int] = set()

    for idx, line in enumerate(payload.lines, start=1):
        order_line_id = int(line.order_line_id)
        if order_line_id in seen_order_line_ids:
            raise HTTPException(
                status_code=409,
                detail=f"duplicate_return_order_line:{order_line_id}",
            )
        seen_order_line_ids.add(order_line_id)

        src = source_map.get(order_line_id)
        if src is None:
            raise HTTPException(
                status_code=404,
                detail=f"return_order_line_not_found:{order_line_id}",
            )

        if int(src.item_id) != int(line.item_id):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"return_order_line_item_mismatch:"
                    f"order_line_id={order_line_id},"
                    f"source_item_id={int(src.item_id)},"
                    f"payload_item_id={int(line.item_id)}"
                ),
            )

        planned_qty = int(line.planned_qty)
        remaining_qty = int(src.qty_remaining_refundable)
        if planned_qty > remaining_qty:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"return_qty_exceeds_remaining:"
                    f"order_line_id={order_line_id},"
                    f"remaining={remaining_qty},"
                    f"planned={planned_qty}"
                ),
            )

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
                "line_no": idx,
                "source_line_id": order_line_id,
                "item_id": int(src.item_id),
                "item_uom_id": int(src.item_uom_id),
                "planned_qty": line.planned_qty,
                "item_name_snapshot": src.item_name_snapshot,
                "item_spec_snapshot": src.item_spec_snapshot,
                "uom_name_snapshot": src.uom_name_snapshot,
                "ratio_to_base_snapshot": src.ratio_to_base_snapshot,
                "remark": line.remark,
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
    "create_inbound_receipt_manual_repo",
    "create_inbound_receipt_from_return_order_repo",
    "release_inbound_receipt_repo",
]
