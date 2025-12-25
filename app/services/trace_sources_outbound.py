# app/services/trace_sources_outbound.py
from __future__ import annotations

from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_types import TraceEvent


async def from_outbound(session: AsyncSession, trace_id: str) -> List[TraceEvent]:
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    id,
                    created_at AS ts,
                    platform,
                    shop_id,
                    ref,
                    state,
                    trace_id
                FROM outbound_commits_v2
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
                source="outbound",
                kind="outbound_v2",
                ref=r["ref"],
                summary=(
                    f"outbound_v2#{r['id']} "
                    f"{r['platform']}/{r['shop_id']} "
                    f"ref={r['ref']} state={r['state']}"
                ),
                raw={
                    "version": "v2",
                    "id": r["id"],
                    "platform": r["platform"],
                    "shop_id": r["shop_id"],
                    "ref": r["ref"],
                    "state": r["state"],
                    "trace_id": r["trace_id"],
                },
            )
        )
    return result
