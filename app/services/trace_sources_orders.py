# app/services/trace_sources_orders.py
from __future__ import annotations

from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_types import TraceEvent


async def from_orders(session: AsyncSession, trace_id: str) -> List[TraceEvent]:
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    id,
                    created_at AS ts
                FROM orders
                WHERE trace_id = :trace_id
                ORDER BY created_at, id
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
                source="order",
                kind="order",
                ref=str(r["id"]),
                summary=f"order#{r['id']}",
                raw={"id": r["id"]},
            )
        )
    return result
