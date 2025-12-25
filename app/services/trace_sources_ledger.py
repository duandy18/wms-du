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
                    id,
                    COALESCE(occurred_at, created_at) AS ts,
                    reason,
                    ref,
                    ref_line,
                    item_id,
                    warehouse_id,
                    batch_code,
                    delta,
                    after_qty
                FROM stock_ledger
                WHERE trace_id = :trace_id
                ORDER BY ts, id
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
                    "id": r["id"],
                },
            )
        )
    return result
