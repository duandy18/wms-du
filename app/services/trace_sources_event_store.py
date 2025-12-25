# app/services/trace_sources_event_store.py
from __future__ import annotations

from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_types import TraceEvent


async def from_event_store(session: AsyncSession, trace_id: str) -> List[TraceEvent]:
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    id,
                    occurred_at AS ts,
                    topic,
                    key,
                    status,
                    payload,
                    headers
                FROM event_store
                WHERE trace_id = :trace_id
                ORDER BY occurred_at, id
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
        topic = r["topic"]
        key = r["key"]
        status = r["status"]
        payload = r["payload"]
        headers = r["headers"]
        result.append(
            TraceEvent(
                ts=ts,
                source="event_store",
                kind=topic or "event",
                ref=key,
                summary=f"{topic or 'event'} key={key} status={status}",
                raw={
                    "topic": topic,
                    "key": key,
                    "status": status,
                    "payload": payload,
                    "headers": headers,
                    "id": r["id"],
                },
            )
        )
    return result
