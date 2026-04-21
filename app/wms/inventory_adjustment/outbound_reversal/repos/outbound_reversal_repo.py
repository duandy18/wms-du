from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_outbound_event_for_reversal(
    session: AsyncSession,
    *,
    event_id: int,
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  id AS event_id,
                  event_no,
                  warehouse_id,
                  source_type,
                  source_ref,
                  occurred_at,
                  committed_at,
                  event_kind,
                  target_event_id,
                  status,
                  remark
                FROM wms_events
                WHERE id = :event_id
                  AND event_type = 'OUTBOUND'
                LIMIT 1
                """
            ),
            {"event_id": int(event_id)},
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail=f"outbound_event_not_found:{int(event_id)}")

    if str(row["event_kind"]) != "COMMIT":
        raise HTTPException(
            status_code=409,
            detail=f"outbound_event_not_reversible_kind:{row['event_kind']}",
        )

    if str(row["status"]) != "COMMITTED":
        raise HTTPException(
            status_code=409,
            detail=f"outbound_event_not_reversible_status:{row['status']}",
        )

    return dict(row)


async def find_committed_outbound_reversal(
    session: AsyncSession,
    *,
    target_event_id: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  event_no,
                  status
                FROM wms_events
                WHERE event_type = 'OUTBOUND'
                  AND event_kind = 'REVERSAL'
                  AND target_event_id = :target_event_id
                  AND status = 'COMMITTED'
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"target_event_id": int(target_event_id)},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_outbound_event_lines_for_reversal(
    session: AsyncSession,
    *,
    event_id: int,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  event_id,
                  ref_line,
                  item_id,
                  qty_outbound,
                  lot_id,
                  lot_code_snapshot,
                  order_line_id,
                  manual_doc_line_id,
                  item_name_snapshot,
                  item_sku_snapshot,
                  item_spec_snapshot,
                  remark,
                  created_at
                FROM outbound_event_lines
                WHERE event_id = :event_id
                ORDER BY ref_line ASC, id ASC
                """
            ),
            {"event_id": int(event_id)},
        )
    ).mappings().all()

    if not rows:
        raise HTTPException(
            status_code=409,
            detail=f"outbound_event_has_no_lines:{int(event_id)}",
        )

    return [dict(r) for r in rows]


async def mark_outbound_event_superseded(
    session: AsyncSession,
    *,
    event_id: int,
) -> None:
    await session.execute(
        text(
            """
            UPDATE wms_events
            SET status = 'SUPERSEDED'
            WHERE id = :event_id
              AND event_type = 'OUTBOUND'
              AND event_kind = 'COMMIT'
              AND status = 'COMMITTED'
            """
        ),
        {"event_id": int(event_id)},
    )


__all__ = [
    "get_outbound_event_for_reversal",
    "find_committed_outbound_reversal",
    "list_outbound_event_lines_for_reversal",
    "mark_outbound_event_superseded",
]
