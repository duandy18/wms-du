from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _norm_text(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


async def list_inbound_reversal_options(
    session: AsyncSession,
    *,
    days: int,
    limit: int,
    source_type: str | None,
) -> list[dict[str, Any]]:
    source_type_norm = _norm_text(source_type)

    if source_type_norm is None:
        stmt = text(
            """
            SELECT
              e.id AS event_id,
              e.event_no,
              e.warehouse_id,
              e.event_kind,
              e.status,
              e.source_type,
              e.source_ref,
              e.occurred_at,
              e.committed_at,
              e.remark,
              COALESCE(COUNT(iel.id), 0) AS line_count,
              COALESCE(SUM(iel.qty_base), 0) AS qty_base_total
            FROM wms_events e
            LEFT JOIN inbound_event_lines iel
              ON iel.event_id = e.id
            WHERE e.event_type = 'INBOUND'
              AND e.event_kind = 'COMMIT'
              AND e.status = 'COMMITTED'
              AND e.committed_at >= (NOW() - make_interval(days => :days))
              AND NOT EXISTS (
                SELECT 1
                FROM wms_events r
                WHERE r.event_type = 'INBOUND'
                  AND r.event_kind = 'REVERSAL'
                  AND r.status = 'COMMITTED'
                  AND r.target_event_id = e.id
              )
            GROUP BY
              e.id,
              e.event_no,
              e.warehouse_id,
              e.event_kind,
              e.status,
              e.source_type,
              e.source_ref,
              e.occurred_at,
              e.committed_at,
              e.remark
            ORDER BY e.committed_at DESC NULLS LAST, e.id DESC
            LIMIT :limit
            """
        )
        params = {
            "days": int(days),
            "limit": int(limit),
        }
    else:
        stmt = text(
            """
            SELECT
              e.id AS event_id,
              e.event_no,
              e.warehouse_id,
              e.event_kind,
              e.status,
              e.source_type,
              e.source_ref,
              e.occurred_at,
              e.committed_at,
              e.remark,
              COALESCE(COUNT(iel.id), 0) AS line_count,
              COALESCE(SUM(iel.qty_base), 0) AS qty_base_total
            FROM wms_events e
            LEFT JOIN inbound_event_lines iel
              ON iel.event_id = e.id
            WHERE e.event_type = 'INBOUND'
              AND e.event_kind = 'COMMIT'
              AND e.status = 'COMMITTED'
              AND e.source_type = :source_type
              AND e.committed_at >= (NOW() - make_interval(days => :days))
              AND NOT EXISTS (
                SELECT 1
                FROM wms_events r
                WHERE r.event_type = 'INBOUND'
                  AND r.event_kind = 'REVERSAL'
                  AND r.status = 'COMMITTED'
                  AND r.target_event_id = e.id
              )
            GROUP BY
              e.id,
              e.event_no,
              e.warehouse_id,
              e.event_kind,
              e.status,
              e.source_type,
              e.source_ref,
              e.occurred_at,
              e.committed_at,
              e.remark
            ORDER BY e.committed_at DESC NULLS LAST, e.id DESC
            LIMIT :limit
            """
        )
        params = {
            "source_type": source_type_norm,
            "days": int(days),
            "limit": int(limit),
        }

    rows = (await session.execute(stmt, params)).mappings().all()
    return [dict(r) for r in rows]


async def get_inbound_event_header(
    session: AsyncSession,
    *,
    event_id: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  e.id AS event_id,
                  e.event_no,
                  e.warehouse_id,
                  e.source_type,
                  e.source_ref,
                  e.occurred_at,
                  e.committed_at,
                  e.event_kind,
                  e.target_event_id,
                  e.status,
                  e.remark,
                  COALESCE(COUNT(iel.id), 0) AS line_count,
                  COALESCE(SUM(iel.qty_base), 0) AS qty_base_total
                FROM wms_events e
                LEFT JOIN inbound_event_lines iel
                  ON iel.event_id = e.id
                WHERE e.id = :event_id
                  AND e.event_type = 'INBOUND'
                GROUP BY
                  e.id,
                  e.event_no,
                  e.warehouse_id,
                  e.source_type,
                  e.source_ref,
                  e.occurred_at,
                  e.committed_at,
                  e.event_kind,
                  e.target_event_id,
                  e.status,
                  e.remark
                LIMIT 1
                """
            ),
            {"event_id": int(event_id)},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_inbound_event_for_reversal(
    session: AsyncSession,
    *,
    event_id: int,
) -> dict[str, Any]:
    row = await get_inbound_event_header(session, event_id=int(event_id))

    if row is None:
        raise HTTPException(status_code=404, detail=f"inbound_event_not_found:{int(event_id)}")

    if str(row["event_kind"]) != "COMMIT":
        raise HTTPException(
            status_code=409,
            detail=f"inbound_event_not_reversible_kind:{row['event_kind']}",
        )

    if str(row["status"]) != "COMMITTED":
        raise HTTPException(
            status_code=409,
            detail=f"inbound_event_not_reversible_status:{row['status']}",
        )

    return row


async def find_committed_inbound_reversal(
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
                WHERE event_type = 'INBOUND'
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


async def list_inbound_event_lines_for_reversal(
    session: AsyncSession,
    *,
    event_id: int,
    require_nonempty: bool = True,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  line_no,
                  item_id,
                  item_name_snapshot,
                  item_spec_snapshot,
                  actual_uom_id,
                  actual_uom_name_snapshot,
                  barcode_input,
                  actual_qty_input,
                  actual_ratio_to_base_snapshot,
                  qty_base,
                  lot_code_input,
                  production_date,
                  expiry_date,
                  lot_id,
                  po_line_id,
                  remark
                FROM inbound_event_lines
                WHERE event_id = :event_id
                ORDER BY line_no ASC, id ASC
                """
            ),
            {"event_id": int(event_id)},
        )
    ).mappings().all()

    if require_nonempty and not rows:
        raise HTTPException(
            status_code=409,
            detail=f"inbound_event_has_no_lines:{int(event_id)}",
        )

    return [dict(r) for r in rows]


async def mark_inbound_event_superseded(
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
              AND event_type = 'INBOUND'
              AND event_kind = 'COMMIT'
              AND status = 'COMMITTED'
            """
        ),
        {"event_id": int(event_id)},
    )


__all__ = [
    "list_inbound_reversal_options",
    "get_inbound_event_header",
    "get_inbound_event_for_reversal",
    "find_committed_inbound_reversal",
    "list_inbound_event_lines_for_reversal",
    "mark_inbound_event_superseded",
]
