from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inbound.repos.item_lookup_repo import get_item_policy_by_id
from app.wms.inbound.repos.lot_resolve_repo import resolve_inbound_lot
from app.wms.receiving.contracts.operation_submit import (
    InboundOperationLineOut,
    InboundOperationSubmitIn,
    InboundOperationSubmitOut,
)

UTC = timezone.utc


def _to_int_exact(value: Decimal, *, label: str) -> int:
    if value != value.to_integral_value():
        raise HTTPException(
            status_code=409,
            detail=f"{label}_must_be_integer_for_stock_sink:{value}",
        )
    return int(value)


def _new_event_no() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"IE-{stamp}-{uuid4().hex[:8].upper()}"


def _new_trace_id() -> str:
    return f"IN-OP-{uuid4().hex[:20]}"


def _map_event_source_type(task_source_type: str) -> str:
    if task_source_type == "RETURN_ORDER":
        return "RETURN"
    return task_source_type


async def _load_item_uom_snapshot(
    session: AsyncSession,
    *,
    item_id: int,
    item_uom_id: int,
) -> tuple[int, str | None, Decimal]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  iu.id AS actual_item_uom_id,
                  COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS actual_uom_name_snapshot,
                  iu.ratio_to_base AS actual_ratio_to_base_snapshot
                FROM item_uoms iu
                WHERE iu.id = :item_uom_id
                  AND iu.item_id = :item_id
                LIMIT 1
                """
            ),
            {
                "item_uom_id": int(item_uom_id),
                "item_id": int(item_id),
            },
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=409,
            detail=f"actual_item_uom_not_found_or_item_mismatch:{item_id}:{item_uom_id}",
        )

    return (
        int(row["actual_item_uom_id"]),
        row["actual_uom_name_snapshot"],
        Decimal(str(row["actual_ratio_to_base_snapshot"])),
    )


async def _resolve_barcode_uom_snapshot(
    session: AsyncSession,
    *,
    item_id: int,
    barcode: str,
) -> tuple[int, str | None, Decimal]:
    code = (barcode or "").strip()
    row = (
        await session.execute(
            text(
                """
                SELECT
                  iu.id AS actual_item_uom_id,
                  COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS actual_uom_name_snapshot,
                  iu.ratio_to_base AS actual_ratio_to_base_snapshot
                FROM item_barcodes ib
                JOIN item_uoms iu
                  ON iu.id = ib.item_uom_id
                 AND iu.item_id = ib.item_id
                WHERE ib.barcode = :barcode
                  AND ib.active = TRUE
                  AND ib.item_id = :item_id
                ORDER BY ib.is_primary DESC, ib.id ASC
                LIMIT 1
                """
            ),
            {
                "barcode": code,
                "item_id": int(item_id),
            },
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=422,
            detail=f"barcode_unbound_or_item_mismatch:{code}",
        )

    return (
        int(row["actual_item_uom_id"]),
        row["actual_uom_name_snapshot"],
        Decimal(str(row["actual_ratio_to_base_snapshot"])),
    )


async def submit_inbound_operation_repo(
    session: AsyncSession,
    *,
    payload: InboundOperationSubmitIn,
    operator_id: int | None,
    operator_name: str | None,
) -> InboundOperationSubmitOut:
    task = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  receipt_no,
                  warehouse_id,
                  warehouse_name_snapshot,
                  supplier_id,
                  counterparty_name_snapshot,
                  status,
                  source_type
                FROM inbound_receipts
                WHERE receipt_no = :receipt_no
                LIMIT 1
                """
            ),
            {"receipt_no": str(payload.receipt_no)},
        )
    ).mappings().first()

    if task is None:
        raise HTTPException(status_code=404, detail="inbound_task_not_found")

    if str(task["status"]) != "RELEASED":
        raise HTTPException(
            status_code=409,
            detail=f"inbound_task_not_released:{task['status']}",
        )

    task_lines = (
        await session.execute(
            text(
                """
                SELECT
                  l.line_no,
                  l.source_line_id,
                  l.item_id,
                  l.item_name_snapshot,
                  l.item_spec_snapshot,
                  l.item_uom_id,
                  l.uom_name_snapshot,
                  l.ratio_to_base_snapshot,
                  l.planned_qty,
                  (l.planned_qty * l.ratio_to_base_snapshot) AS planned_qty_base,
                  COALESCE(SUM(ol.qty_base), 0) AS received_qty_base
                FROM inbound_receipt_lines l
                LEFT JOIN wms_inbound_operations o
                  ON o.receipt_no_snapshot = :receipt_no
                LEFT JOIN wms_inbound_operation_lines ol
                  ON ol.wms_inbound_operation_id = o.id
                 AND ol.receipt_line_no_snapshot = l.line_no
                WHERE l.inbound_receipt_id = :receipt_id
                GROUP BY
                  l.line_no,
                  l.source_line_id,
                  l.item_id,
                  l.item_name_snapshot,
                  l.item_spec_snapshot,
                  l.item_uom_id,
                  l.uom_name_snapshot,
                  l.ratio_to_base_snapshot,
                  l.planned_qty
                ORDER BY l.line_no ASC
                """
            ),
            {
                "receipt_no": str(payload.receipt_no),
                "receipt_id": int(task["id"]),
            },
        )
    ).mappings().all()

    line_map = {int(r["line_no"]): r for r in task_lines}

    operated_at = datetime.now(UTC)

    op_header = (
        await session.execute(
            text(
                """
                INSERT INTO wms_inbound_operations (
                  receipt_no_snapshot,
                  warehouse_id,
                  warehouse_name_snapshot,
                  supplier_id,
                  supplier_name_snapshot,
                  operator_id,
                  operator_name_snapshot,
                  operated_at,
                  remark
                )
                VALUES (
                  :receipt_no_snapshot,
                  :warehouse_id,
                  :warehouse_name_snapshot,
                  :supplier_id,
                  :supplier_name_snapshot,
                  :operator_id,
                  :operator_name_snapshot,
                  :operated_at,
                  :remark
                )
                RETURNING id
                """
            ),
            {
                "receipt_no_snapshot": str(task["receipt_no"]),
                "warehouse_id": int(task["warehouse_id"]),
                "warehouse_name_snapshot": task["warehouse_name_snapshot"],
                "supplier_id": task["supplier_id"],
                "supplier_name_snapshot": task["counterparty_name_snapshot"],
                "operator_id": operator_id,
                "operator_name_snapshot": operator_name,
                "operated_at": operated_at,
                "remark": payload.remark,
            },
        )
    ).mappings().first()

    operation_id = int(op_header["id"])

    event_source_type = _map_event_source_type(str(task["source_type"]))
    event_no = _new_event_no()
    trace_id = _new_trace_id()

    event_row = (
        await session.execute(
            text(
                """
                INSERT INTO wms_events (
                  event_no,
                  event_type,
                  warehouse_id,
                  source_type,
                  source_ref,
                  occurred_at,
                  trace_id,
                  event_kind,
                  status,
                  created_by,
                  remark
                )
                VALUES (
                  :event_no,
                  'INBOUND',
                  :warehouse_id,
                  :source_type,
                  :source_ref,
                  :occurred_at,
                  :trace_id,
                  'COMMIT',
                  'COMMITTED',
                  :created_by,
                  :remark
                )
                RETURNING id
                """
            ),
            {
                "event_no": event_no,
                "warehouse_id": int(task["warehouse_id"]),
                "source_type": event_source_type,
                "source_ref": str(task["receipt_no"]),
                "occurred_at": operated_at,
                "trace_id": trace_id,
                "created_by": operator_id,
                "remark": payload.remark,
            },
        )
    ).mappings().first()

    event_id = int(event_row["id"])

    out_lines: list[InboundOperationLineOut] = []
    event_line_no = 0

    for line in payload.lines:
        task_line = line_map.get(int(line.receipt_line_no))
        if task_line is None:
            raise HTTPException(
                status_code=404,
                detail=f"inbound_task_line_not_found:{line.receipt_line_no}",
            )

        task_item_id = int(task_line["item_id"])
        task_item_uom_id = int(task_line["item_uom_id"])
        task_uom_name_snapshot = task_line["uom_name_snapshot"]
        task_ratio = Decimal(str(task_line["ratio_to_base_snapshot"]))
        planned_qty_base = Decimal(str(task_line["planned_qty_base"]))
        received_qty_base_running = Decimal(str(task_line["received_qty_base"]))

        item_policy = await get_item_policy_by_id(
            session,
            item_id=task_item_id,
        )
        if item_policy is None:
            raise HTTPException(
                status_code=404,
                detail=f"item_policy_not_found:{task_item_id}",
            )

        for entry in line.entries:
            qty_inbound = Decimal(str(entry.qty_inbound))
            barcode_input = (
                str(entry.barcode_input).strip()
                if entry.barcode_input is not None
                else None
            ) or None
            explicit_actual_item_uom_id = (
                int(entry.actual_item_uom_id)
                if entry.actual_item_uom_id is not None
                else None
            )

            if barcode_input is not None:
                (
                    actual_item_uom_id,
                    actual_uom_name_snapshot,
                    actual_ratio,
                ) = await _resolve_barcode_uom_snapshot(
                    session,
                    item_id=task_item_id,
                    barcode=barcode_input,
                )
                if (
                    explicit_actual_item_uom_id is not None
                    and explicit_actual_item_uom_id != actual_item_uom_id
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=f"barcode_actual_item_uom_mismatch:{line.receipt_line_no}",
                    )
            elif explicit_actual_item_uom_id is not None:
                (
                    actual_item_uom_id,
                    actual_uom_name_snapshot,
                    actual_ratio,
                ) = await _load_item_uom_snapshot(
                    session,
                    item_id=task_item_id,
                    item_uom_id=explicit_actual_item_uom_id,
                )
            else:
                actual_item_uom_id = task_item_uom_id
                actual_uom_name_snapshot = task_uom_name_snapshot
                actual_ratio = task_ratio

            qty_base = qty_inbound * actual_ratio

            if received_qty_base_running + qty_base > planned_qty_base:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"received_qty_base_exceeds_planned:"
                        f"line={line.receipt_line_no}:"
                        f"planned_base={planned_qty_base}:"
                        f"received_base={received_qty_base_running}:"
                        f"incoming_base={qty_base}"
                    ),
                )

            qty_base_int = _to_int_exact(qty_base, label="qty_base")
            qty_input_int = _to_int_exact(qty_inbound, label="actual_qty_input")
            actual_ratio_int = _to_int_exact(actual_ratio, label="actual_ratio_to_base")

            lot_id = await resolve_inbound_lot(
                session,
                warehouse_id=int(task["warehouse_id"]),
                item_policy=item_policy,
                lot_code=entry.batch_no,
                production_date=entry.production_date,
                expiry_date=entry.expiry_date,
            )

            inserted = (
                await session.execute(
                    text(
                        """
                        INSERT INTO wms_inbound_operation_lines (
                          wms_inbound_operation_id,
                          receipt_line_no_snapshot,
                          item_id,
                          item_name_snapshot,
                          item_spec_snapshot,
                          actual_item_uom_id,
                          actual_uom_name_snapshot,
                          actual_ratio_to_base_snapshot,
                          actual_qty_input,
                          qty_base,
                          batch_no,
                          production_date,
                          expiry_date,
                          lot_id,
                          remark
                        )
                        VALUES (
                          :wms_inbound_operation_id,
                          :receipt_line_no_snapshot,
                          :item_id,
                          :item_name_snapshot,
                          :item_spec_snapshot,
                          :actual_item_uom_id,
                          :actual_uom_name_snapshot,
                          :actual_ratio_to_base_snapshot,
                          :actual_qty_input,
                          :qty_base,
                          :batch_no,
                          :production_date,
                          :expiry_date,
                          :lot_id,
                          :remark
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "wms_inbound_operation_id": operation_id,
                        "receipt_line_no_snapshot": int(line.receipt_line_no),
                        "item_id": task_item_id,
                        "item_name_snapshot": task_line["item_name_snapshot"],
                        "item_spec_snapshot": task_line["item_spec_snapshot"],
                        "actual_item_uom_id": actual_item_uom_id,
                        "actual_uom_name_snapshot": actual_uom_name_snapshot,
                        "actual_ratio_to_base_snapshot": actual_ratio,
                        "actual_qty_input": qty_inbound,
                        "qty_base": qty_base,
                        "batch_no": entry.batch_no,
                        "production_date": entry.production_date,
                        "expiry_date": entry.expiry_date,
                        "lot_id": int(lot_id) if lot_id is not None else None,
                        "remark": entry.remark,
                    },
                )
            ).mappings().first()

            event_line_no += 1
            po_line_id = (
                int(task_line["source_line_id"])
                if str(task["source_type"]) == "PURCHASE_ORDER" and task_line["source_line_id"] is not None
                else None
            )

            await session.execute(
                text(
                    """
                    INSERT INTO inbound_event_lines (
                      event_id,
                      line_no,
                      item_id,
                      actual_uom_id,
                      barcode_input,
                      actual_qty_input,
                      actual_ratio_to_base_snapshot,
                      qty_base,
                      lot_code_input,
                      production_date,
                      expiry_date,
                      lot_id,
                      po_line_id,
                      remark
                    )
                    VALUES (
                      :event_id,
                      :line_no,
                      :item_id,
                      :actual_uom_id,
                      :barcode_input,
                      :actual_qty_input,
                      :actual_ratio_to_base_snapshot,
                      :qty_base,
                      :lot_code_input,
                      :production_date,
                      :expiry_date,
                      :lot_id,
                      :po_line_id,
                      :remark
                    )
                    """
                ),
                {
                    "event_id": event_id,
                    "line_no": event_line_no,
                    "item_id": task_item_id,
                    "actual_uom_id": actual_item_uom_id,
                    "barcode_input": barcode_input,
                    "actual_qty_input": qty_input_int,
                    "actual_ratio_to_base_snapshot": actual_ratio_int,
                    "qty_base": qty_base_int,
                    "lot_code_input": entry.batch_no,
                    "production_date": entry.production_date,
                    "expiry_date": entry.expiry_date,
                    "lot_id": int(lot_id) if lot_id is not None else None,
                    "po_line_id": po_line_id,
                    "remark": entry.remark,
                },
            )

            qty_row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO stocks_lot (
                          item_id,
                          warehouse_id,
                          lot_id,
                          qty
                        )
                        VALUES (
                          :item_id,
                          :warehouse_id,
                          :lot_id,
                          :delta
                        )
                        ON CONFLICT (item_id, warehouse_id, lot_id)
                        DO UPDATE
                        SET qty = stocks_lot.qty + EXCLUDED.qty
                        RETURNING qty
                        """
                    ),
                    {
                        "item_id": task_item_id,
                        "warehouse_id": int(task["warehouse_id"]),
                        "lot_id": int(lot_id),
                        "delta": qty_base_int,
                    },
                )
            ).mappings().first()

            after_qty = int(qty_row["qty"])

            await session.execute(
                text(
                    """
                    INSERT INTO stock_ledger (
                      reason,
                      after_qty,
                      delta,
                      occurred_at,
                      ref,
                      ref_line,
                      item_id,
                      warehouse_id,
                      trace_id,
                      production_date,
                      expiry_date,
                      sub_reason,
                      reason_canon,
                      lot_id,
                      event_id
                    )
                    VALUES (
                      'RECEIPT',
                      :after_qty,
                      :delta,
                      :occurred_at,
                      :ref,
                      :ref_line,
                      :item_id,
                      :warehouse_id,
                      :trace_id,
                      :production_date,
                      :expiry_date,
                      'INBOUND_OPERATION',
                      'RECEIPT',
                      :lot_id,
                      :event_id
                    )
                    """
                ),
                {
                    "after_qty": after_qty,
                    "delta": qty_base_int,
                    "occurred_at": operated_at,
                    "ref": event_no,
                    "ref_line": event_line_no,
                    "item_id": task_item_id,
                    "warehouse_id": int(task["warehouse_id"]),
                    "trace_id": trace_id,
                    "production_date": entry.production_date,
                    "expiry_date": entry.expiry_date,
                    "lot_id": int(lot_id),
                    "event_id": event_id,
                },
            )

            out_lines.append(
                InboundOperationLineOut(
                    id=int(inserted["id"]),
                    receipt_line_no_snapshot=int(line.receipt_line_no),
                    item_id=task_item_id,
                    item_name_snapshot=task_line["item_name_snapshot"],
                    item_spec_snapshot=task_line["item_spec_snapshot"],
                    actual_item_uom_id=actual_item_uom_id,
                    actual_uom_name_snapshot=actual_uom_name_snapshot,
                    actual_ratio_to_base_snapshot=actual_ratio,
                    actual_qty_input=qty_inbound,
                    qty_base=qty_base,
                    batch_no=entry.batch_no,
                    production_date=entry.production_date,
                    expiry_date=entry.expiry_date,
                    lot_id=int(lot_id) if lot_id is not None else None,
                    remark=entry.remark,
                )
            )

            received_qty_base_running += qty_base

    return InboundOperationSubmitOut(
        id=operation_id,
        receipt_no_snapshot=str(task["receipt_no"]),
        warehouse_id=int(task["warehouse_id"]),
        warehouse_name_snapshot=task["warehouse_name_snapshot"],
        supplier_id=task["supplier_id"],
        supplier_name_snapshot=task["counterparty_name_snapshot"],
        operator_id=operator_id,
        operator_name_snapshot=operator_name,
        operated_at=operated_at,
        remark=payload.remark,
        lines=out_lines,
    )


__all__ = [
    "submit_inbound_operation_repo",
]
