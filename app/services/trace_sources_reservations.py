# app/services/trace_sources_reservations.py
from __future__ import annotations

from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_types import TraceEvent


async def from_reservations(session: AsyncSession, trace_id: str) -> List[TraceEvent]:
    # reservation 头：按 trace_id 聚合
    rows_head = (
        (
            await session.execute(
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
                    f"res#{rid} {r['status']} {r['platform']}/{r['shop_id']} wh={r['warehouse_id']}"
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
            await session.execute(
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
                    f"res#{rid} line#{ref_line} item={item_id} qty={qty} consumed={consumed_qty}"
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
                    summary=(f"res#{rid} consumed item={item_id} consumed_qty={consumed_int}"),
                    raw={
                        "reservation_id": rid,
                        "item_id": item_id,
                        "consumed_qty": consumed_int,
                        "ref_line": ref_line,
                    },
                )
            )

    return events
