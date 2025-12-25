# app/services/trace_sources_audit.py
from __future__ import annotations

from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_types import TraceEvent


async def from_audit_events(session: AsyncSession, trace_id: str) -> List[TraceEvent]:
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    id,
                    created_at AS ts,
                    category,
                    ref,
                    meta
                FROM audit_events
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
        ts = r["ts"]
        category = r["category"]
        ref = r["ref"]
        meta = r["meta"] or {}
        event = meta.get("event")
        flow = meta.get("flow")

        summary_parts = [f"audit {category or 'event'} ref={ref}"]
        if flow:
            summary_parts.append(f"flow={flow}")
        if event:
            summary_parts.append(f"event={event}")

        result.append(
            TraceEvent(
                ts=ts,
                source="audit",
                kind=category or "audit",
                ref=ref,
                summary=" ".join(summary_parts),
                raw={
                    "category": category,
                    "ref": ref,
                    "meta": meta,
                    "id": r["id"],
                },
            )
        )
    return result
