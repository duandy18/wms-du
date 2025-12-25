# app/services/trace_service.py
from __future__ import annotations

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_normalize import normalize_ts
from app.services.trace_sources import (
    from_audit_events,
    from_event_store,
    from_ledger,
    from_orders,
    from_outbound,
    from_reservations,
)
from app.services.trace_types import TraceEvent, TraceResult


class TraceService:
    """
    Trace 黑盒（统一 trace_id 版本）

    - 聚合键：trace_id
    - 数据源：
        * event_store.trace_id
        * audit_events.trace_id
        * reservations.trace_id
        * reservation_lines（通过 reservations.id）
        * stock_ledger.trace_id
        * orders.trace_id
        * outbound_commits_v2.trace_id

    - Ship v3：
        * reservation_lines.consumed_qty > 0 时增加 reservation_consumed 事件
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_trace(self, trace_id: str) -> TraceResult:
        events: List[TraceEvent] = []

        events.extend(await from_event_store(self.session, trace_id))
        events.extend(await from_audit_events(self.session, trace_id))
        events.extend(await from_reservations(self.session, trace_id))
        events.extend(await from_ledger(self.session, trace_id))
        events.extend(await from_orders(self.session, trace_id))
        events.extend(await from_outbound(self.session, trace_id))

        normalized: List[TraceEvent] = []
        for e in events:
            ts = normalize_ts(e.ts)
            if ts is None:
                continue
            e.ts = ts
            normalized.append(e)

        normalized.sort(key=lambda e: e.ts)
        return TraceResult(trace_id=trace_id, events=normalized)


__all__ = [
    "TraceService",
    "TraceEvent",
    "TraceResult",
]
