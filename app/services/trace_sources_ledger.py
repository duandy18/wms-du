# app/services/trace_sources_ledger.py
from __future__ import annotations

from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_types import TraceEvent


async def from_ledger(session: AsyncSession, trace_id: str) -> List[TraceEvent]:
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    sl.id,
                    COALESCE(sl.occurred_at, sl.created_at) AS ts,
                    sl.reason,
                    sl.ref,
                    sl.ref_line,
                    sl.item_id,
                    sl.warehouse_id,
                    lo.lot_code AS batch_code,
                    sl.delta,
                    sl.after_qty,
                    sl.lot_id
                FROM stock_ledger sl
                JOIN lots lo
                  ON lo.id = sl.lot_id
                 AND lo.warehouse_id = sl.warehouse_id
                 AND lo.item_id = sl.item_id
                WHERE sl.trace_id = :trace_id
                ORDER BY ts, sl.id
                """
                ),
                {"trace_id": trace_id},
            )
        )
        .mappings()
        .all()
    )

    result: List[TraceEvent] = []
    for r in rows:
        result.append(
            TraceEvent(
                ts=r["ts"],
                source="ledger",
                kind=r["reason"] or "LEDGER",
                ref=r["ref"],
                summary=(
                    f"ledger {r['reason']} ref={r['ref']}/{r['ref_line']} "
                    f"item={r['item_id']} wh={r['warehouse_id']} "
                    f"batch={r['batch_code']} delta={r['delta']} "
                    f"after={r['after_qty']}"
                ),
                raw={
                    "reason": r["reason"],
                    "ref": r["ref"],
                    "ref_line": r["ref_line"],
                    "item_id": r["item_id"],
                    "warehouse_id": r["warehouse_id"],
                    "batch_code": r["batch_code"],
                    "delta": r["delta"],
                    "after_qty": r["after_qty"],
                    "lot_id": r["lot_id"],
                    "id": r["id"],
                },
            )
        )
    return result
