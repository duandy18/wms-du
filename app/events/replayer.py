# app/events/replayer.py
from __future__ import annotations
from typing import Callable, Awaitable, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry import trace

from app.events.models_event_store import EventRow

Tracer = trace.get_tracer(__name__)

class ReplayError(Exception):
    ...


async def replay(
    session: AsyncSession,
    topic: str,
    handler: Callable[[dict | None], Awaitable[None]],
    limit: int = 100,
    only_status: Tuple[str, ...] = ("PENDING", "DLQ"),
    key_prefix: Optional[str] = None,
):
    stmt = select(EventRow).where(
        EventRow.topic == topic,
        EventRow.status.in_(only_status),
    ).order_by(EventRow.id).limit(limit)
    if key_prefix:
        stmt = stmt.where(EventRow.key.like(f"{key_prefix}%"))
    rows = (await session.execute(stmt)).scalars().all()

    for row in rows:
        with Tracer.start_as_current_span(
            "event.replay",
            attributes={"topic": topic, "event.id": row.id, "event.key": row.key or ""},
        ):
            try:
                await handler(row.payload if isinstance(row.payload, dict) else None)
                await session.execute(
                    update(EventRow)
                    .where(EventRow.id == row.id)
                    .values(status="CONSUMED", attempts=row.attempts + 1, last_error=None)
                )
                # 审计 repair
                await audit_repair(session, row, note="auto repair by replay")
            except Exception as e:
                await session.execute(
                    update(EventRow)
                    .where(EventRow.id == row.id)
                    .values(status="DLQ", attempts=row.attempts + 1, last_error=str(e))
                )
    await session.commit()


async def audit_repair(session: AsyncSession, original: EventRow, note: str = "") -> None:
    """
    修复动作审计：落一条 topic='repair'，key = "<src_topic>:<src_key>:<src_id>"
    幂等：on_conflict_do_nothing(index_elements=['topic','key'])
    """
    audit_payload = {
        "note": note,
        "src_topic": original.topic,
        "src_key": original.key,
        "src_id": original.id,
        "src_attempts": original.attempts,
        "src_last_error": original.last_error,
    }
    stmt = (
        pg_insert(EventRow.__table__)
        .values(
            topic="repair",
            key=f"{original.topic}:{original.key}:{original.id}",
            payload=audit_payload,
            headers={"source": "replayer"},
            status="PENDING",
            attempts=0,
            trace_id=original.trace_id,
            checksum=None,
        )
        .on_conflict_do_nothing(index_elements=["topic", "key"])
    )
    await session.execute(stmt)
