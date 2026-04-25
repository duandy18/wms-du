# app/wms/outbound/repos/outbound_event_repo.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def insert_outbound_event(
    session: AsyncSession,
    *,
    warehouse_id: int,
    source_type: str,
    source_ref: str,
    occurred_at: datetime,
    trace_id: str,
    created_by: int | None,
    remark: str | None,
) -> Mapping[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO wms_events (
                      event_no,
                      warehouse_id,
                      source_type,
                      source_ref,
                      occurred_at,
                      trace_id,
                      event_kind,
                      status,
                      created_by,
                      remark,
                      event_type
                    )
                    VALUES (
                      :event_no,
                      :warehouse_id,
                      :source_type,
                      :source_ref,
                      :occurred_at,
                      :trace_id,
                      'COMMIT',
                      'COMMITTED',
                      :created_by,
                      :remark,
                      'OUTBOUND'
                    )
                    RETURNING
                      id,
                      event_no,
                      warehouse_id,
                      source_type,
                      source_ref,
                      occurred_at,
                      committed_at,
                      trace_id,
                      event_type,
                      status,
                      created_by,
                      remark
                    """
                ),
                {
                    "event_no": str(trace_id)[:64],
                    "warehouse_id": int(warehouse_id),
                    "source_type": str(source_type),
                    "source_ref": str(source_ref),
                    "occurred_at": occurred_at,
                    "trace_id": str(trace_id),
                    "created_by": int(created_by) if created_by is not None else None,
                    "remark": str(remark).strip() if remark else None,
                },
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError("insert_outbound_event_failed")
    return row


async def insert_outbound_event_lines(
    session: AsyncSession,
    *,
    event_id: int,
    lines: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for ln in lines:
        row = (
            (
                await session.execute(
                    text(
                        """
                        INSERT INTO outbound_event_lines (
                          event_id,
                          ref_line,
                          item_id,
                          qty_outbound,
                          lot_id,
                          lot_code_snapshot,
                          order_line_id,
                          manual_doc_line_id,
                          item_name_snapshot,
                          item_sku_snapshot,
                          item_spec_snapshot,
                          remark
                        )
                        VALUES (
                          :event_id,
                          :ref_line,
                          :item_id,
                          :qty_outbound,
                          :lot_id,
                          :lot_code_snapshot,
                          :order_line_id,
                          :manual_doc_line_id,
                          :item_name_snapshot,
                          :item_sku_snapshot,
                          :item_spec_snapshot,
                          :remark
                        )
                        RETURNING
                          id,
                          event_id,
                          ref_line,
                          item_id,
                          qty_outbound,
                          lot_id,
                          lot_code_snapshot,
                          order_line_id,
                          manual_doc_line_id,
                          item_name_snapshot,
                          item_sku_snapshot,
                          item_spec_snapshot,
                          remark,
                          created_at
                        """
                    ),
                    {
                        "event_id": int(event_id),
                        "ref_line": int(ln["ref_line"]),
                        "item_id": int(ln["item_id"]),
                        "qty_outbound": int(ln["qty_outbound"]),
                        "lot_id": int(ln["lot_id"]),
                        "lot_code_snapshot": ln.get("lot_code_snapshot"),
                        "order_line_id": ln.get("order_line_id"),
                        "manual_doc_line_id": ln.get("manual_doc_line_id"),
                        "item_name_snapshot": ln.get("item_name_snapshot"),
                        "item_sku_snapshot": ln.get("item_sku_snapshot"),
                        "item_spec_snapshot": ln.get("item_spec_snapshot"),
                        "remark": ln.get("remark"),
                    },
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise ValueError("insert_outbound_event_line_failed")
        out.append(dict(row))

    return out


async def load_stocks_lot_for_update(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
) -> int | None:
    row = (
        await session.execute(
            text(
                """
                SELECT qty
                FROM stocks_lot
                WHERE warehouse_id = :warehouse_id
                  AND item_id = :item_id
                  AND lot_id = :lot_id
                FOR UPDATE
                """
            ),
            {
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "lot_id": int(lot_id),
            },
        )
    ).first()
    if not row:
        return None
    return int(row[0])


async def update_stocks_lot_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
    qty: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE stocks_lot
            SET qty = :qty
            WHERE warehouse_id = :warehouse_id
              AND item_id = :item_id
              AND lot_id = :lot_id
            """
        ),
        {
            "qty": int(qty),
            "warehouse_id": int(warehouse_id),
            "item_id": int(item_id),
            "lot_id": int(lot_id),
        },
    )


async def insert_outbound_stock_ledger(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: int,
    qty_outbound: int,
    after_qty: int,
    occurred_at: datetime,
    source_ref: str,
    ref_line: int,
    trace_id: str,
    event_id: int,
) -> None:
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
              sub_reason,
              reason_canon,
              lot_id,
              event_id
            )
            VALUES (
              'OUTBOUND_SHIP',
              :after_qty,
              :delta,
              :occurred_at,
              :ref,
              :ref_line,
              :item_id,
              :warehouse_id,
              :trace_id,
              'ORDER_OUTBOUND',
              'OUTBOUND',
              :lot_id,
              :event_id
            )
            """
        ),
        {
            "after_qty": int(after_qty),
            "delta": -int(qty_outbound),
            "occurred_at": occurred_at,
            "ref": str(source_ref),
            "ref_line": int(ref_line),
            "item_id": int(item_id),
            "warehouse_id": int(warehouse_id),
            "trace_id": str(trace_id),
            "lot_id": int(lot_id),
            "event_id": int(event_id),
        },
    )
