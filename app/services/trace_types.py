# app/services/trace_types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal

TraceSource = Literal[
    "event_store",
    "audit",
    "reservation",
    "reservation_line",
    "reservation_consumed",  # 预占被消耗
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

    @property
    def reservation_consumption(self) -> Dict[int, Dict[int, Dict[str, int]]]:
        """
        汇总预占消耗情况（调试辅助）：
        {
          reservation_id: {
            item_id: {"qty": 总预占, "consumed": 总消耗},
            ...
          },
          ...
        }
        数据来源：
          - source="reservation_line" 的事件，读取 qty / consumed_qty。
        """
        result: Dict[int, Dict[int, Dict[str, int]]] = {}
        for e in self.events:
            if e.source != "reservation_line":
                continue
            rid = int(e.raw.get("reservation_id", 0))
            item_id = int(e.raw.get("item_id", 0))
            qty = int(e.raw.get("qty", 0))
            consumed = int(e.raw.get("consumed_qty", 0))
            if rid <= 0 or item_id <= 0:
                continue
            per_res = result.setdefault(rid, {})
            rec = per_res.setdefault(item_id, {"qty": 0, "consumed": 0})
            rec["qty"] += qty
            rec["consumed"] += consumed
        return result
