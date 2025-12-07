from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

    def _normalize_ts(self, ts: datetime | None) -> datetime | None:
        """
        统一时间为 tz-aware UTC，避免 naive / aware 混用导致排序报错。
        """
        if ts is None:
            return None
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    async def get_trace(self, trace_id: str) -> TraceResult:
        events: List[TraceEvent] = []

        # 只按 trace_id 聚合；不再做 ref / dedup / event_log 兜底
        events.extend(await self._from_event_store(trace_id))
        events.extend(await self._from_audit_events(trace_id))
        events.extend(await self._from_reservations(trace_id))
        events.extend(await self._from_ledger(trace_id))
        events.extend(await self._from_orders(trace_id))
        events.extend(await self._from_outbound(trace_id))

        # 过滤掉没有 ts 的，并统一成 tz-aware，再按时间排序
        normalized: List[TraceEvent] = []
        for e in events:
            ts = self._normalize_ts(e.ts)
            if ts is None:
                continue
            e.ts = ts
            normalized.append(e)

        normalized.sort(key=lambda e: e.ts)

        return TraceResult(trace_id=trace_id, events=normalized)

    # ------------------------------------------------------------------
    # event_store
    # ------------------------------------------------------------------

    async def _from_event_store(self, trace_id: str) -> List[TraceEvent]:
        rows = (
            (
                await self.session.execute(
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

    # ------------------------------------------------------------------
    # audit_events
    # ------------------------------------------------------------------

    async def _from_audit_events(self, trace_id: str) -> List[TraceEvent]:
        rows = (
            (
                await self.session.execute(
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

    # ------------------------------------------------------------------
    # reservations + reservation_lines + reservation_consumed
    # ------------------------------------------------------------------

    async def _from_reservations(self, trace_id: str) -> List[TraceEvent]:
        # reservation 头：按 trace_id 聚合
        rows_head = (
            (
                await self.session.execute(
                    text(
                        """
                    SELECT
                        id,
                        created_at AS ts,
                        platform,
                        shop_id,
                        warehouse_id,
                        ref,
                        status,
                        expire_at,
                        released_at,
                        trace_id
                    FROM reservations
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

        events: List[TraceEvent] = []
        res_ids: List[int] = []

        for r in rows_head:
            rid = int(r["id"])
            res_ids.append(rid)

            events.append(
                TraceEvent(
                    ts=r["ts"],
                    source="reservation",
                    kind=f"reservation_{r['status']}",
                    ref=r["ref"],
                    summary=(
                        f"res#{rid} {r['status']} "
                        f"{r['platform']}/{r['shop_id']} "
                        f"wh={r['warehouse_id']}"
                    ),
                    raw={
                        "id": rid,
                        "platform": r["platform"],
                        "shop_id": r["shop_id"],
                        "warehouse_id": r["warehouse_id"],
                        "ref": r["ref"],
                        "status": r["status"],
                        "expire_at": r["expire_at"],
                        "released_at": r["released_at"],
                        "trace_id": r["trace_id"],
                    },
                )
            )

        if not res_ids:
            return events

        # reservation_lines
        rows_lines = (
            (
                await self.session.execute(
                    text(
                        """
                    SELECT
                        id,
                        reservation_id,
                        created_at AS ts,
                        updated_at,
                        item_id,
                        qty,
                        consumed_qty,
                        ref_line
                    FROM reservation_lines
                    WHERE reservation_id = ANY(:ids)
                    ORDER BY created_at, id
                    """
                    ),
                    {"ids": res_ids},
                )
            )
            .mappings()
            .all()
        )

        for r in rows_lines:
            rid = int(r["reservation_id"])
            ts_line = r["ts"]
            ts_updated = r["updated_at"] or ts_line
            item_id = r["item_id"]
            qty = r["qty"]
            consumed_qty = r["consumed_qty"]
            ref_line = r["ref_line"]

            # 行事件
            events.append(
                TraceEvent(
                    ts=ts_line,
                    source="reservation_line",
                    kind="reservation_line",
                    ref=None,
                    summary=(
                        f"res#{rid} line#{ref_line} "
                        f"item={item_id} qty={qty} consumed={consumed_qty}"
                    ),
                    raw={
                        "reservation_id": rid,
                        "item_id": item_id,
                        "qty": qty,
                        "consumed_qty": consumed_qty,
                        "ref_line": ref_line,
                    },
                )
            )

            # consumed 事件
            consumed_int = int(consumed_qty or 0)
            if consumed_int > 0:
                events.append(
                    TraceEvent(
                        ts=ts_updated,
                        source="reservation_consumed",
                        kind="reservation_consumed",
                        ref=None,
                        summary=(
                            f"res#{rid} consumed item={item_id} "
                            f"consumed_qty={consumed_int}"
                        ),
                        raw={
                            "reservation_id": rid,
                            "item_id": item_id,
                            "consumed_qty": consumed_int,
                            "ref_line": ref_line,
                        },
                    )
                )

        return events

    # ------------------------------------------------------------------
    # ledger
    # ------------------------------------------------------------------

    async def _from_ledger(self, trace_id: str) -> List[TraceEvent]:
        rows = (
            (
                await self.session.execute(
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

    # ------------------------------------------------------------------
    # orders
    # ------------------------------------------------------------------

    async def _from_orders(self, trace_id: str) -> List[TraceEvent]:
        rows = (
            (
                await self.session.execute(
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

    # ------------------------------------------------------------------
    # outbound v2
    # ------------------------------------------------------------------

    async def _from_outbound(self, trace_id: str) -> List[TraceEvent]:
        rows = (
            (
                await self.session.execute(
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
