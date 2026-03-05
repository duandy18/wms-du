# app/services/trace_types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Literal


TraceSource = Literal[
    "event_store",
    "audit",
    "ledger",
    "order",
    "outbound",
]


@dataclass
class TraceEvent:
    ts: datetime
    source: TraceSource
    kind: str
    ref: str | None
    summary: str
    raw: dict[str, Any]


@dataclass
class TraceResult:
    trace_id: str
    events: List[TraceEvent]

    @property
    def started_at(self) -> datetime | None:
        return self.events[0].ts if self.events else None

    @property
    def last_seen_at(self) -> datetime | None:
        return self.events[-1].ts if self.events else None
