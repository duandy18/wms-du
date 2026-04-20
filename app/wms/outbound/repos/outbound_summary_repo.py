# app/wms/outbound/repos/outbound_summary_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _build_where(
    *,
    source_type: Optional[str],
    warehouse_id: Optional[int],
    status: Optional[str],
) -> tuple[str, Dict[str, Any]]:
    clauses = ["e.event_type = 'OUTBOUND'"]
    params: Dict[str, Any] = {}

    if source_type:
        clauses.append("e.source_type = :source_type")
        params["source_type"] = str(source_type).upper().strip()

    if warehouse_id is not None:
        clauses.append("e.warehouse_id = :warehouse_id")
        params["warehouse_id"] = int(warehouse_id)

    if status:
        clauses.append("e.status = :status")
        params["status"] = str(status).upper().strip()

    return " AND ".join(clauses), params


async def list_outbound_summary(
    session: AsyncSession,
    *,
    source_type: Optional[str],
    warehouse_id: Optional[int],
    status: Optional[str],
    limit: int,
    offset: int,
) -> List[Dict[str, Any]]:
    where_sql, params = _build_where(
        source_type=source_type,
        warehouse_id=warehouse_id,
        status=status,
    )
    params.update({"limit": int(limit), "offset": int(offset)})

    rows = (
        (
            await session.execute(
                text(
                    f"""
                    SELECT
                      e.id AS event_id,
                      e.event_no,
                      e.event_type,
                      e.source_type,
                      e.source_ref,
                      e.warehouse_id,
                      e.occurred_at,
                      e.committed_at,
                      e.trace_id,
                      e.status,
                      e.created_by,
                      e.remark,
                      COALESCE(a.lines_count, 0) AS lines_count,
                      COALESCE(a.total_qty_outbound, 0) AS total_qty_outbound
                    FROM wms_events e
                    LEFT JOIN (
                      SELECT
                        event_id,
                        COUNT(*) AS lines_count,
                        COALESCE(SUM(qty_outbound), 0) AS total_qty_outbound
                      FROM outbound_event_lines
                      GROUP BY event_id
                    ) a
                      ON a.event_id = e.id
                    WHERE {where_sql}
                    ORDER BY e.occurred_at DESC, e.id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def count_outbound_summary(
    session: AsyncSession,
    *,
    source_type: Optional[str],
    warehouse_id: Optional[int],
    status: Optional[str],
) -> int:
    where_sql, params = _build_where(
        source_type=source_type,
        warehouse_id=warehouse_id,
        status=status,
    )
    row = (
        await session.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM wms_events e
                WHERE {where_sql}
                """
            ),
            params,
        )
    ).first()
    return int(row[0] if row else 0)


async def get_outbound_summary_event(
    session: AsyncSession,
    *,
    event_id: int,
) -> Mapping[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      e.id AS event_id,
                      e.event_no,
                      e.event_type,
                      e.source_type,
                      e.source_ref,
                      e.warehouse_id,
                      e.occurred_at,
                      e.committed_at,
                      e.trace_id,
                      e.status,
                      e.created_by,
                      e.remark,
                      COALESCE(a.lines_count, 0) AS lines_count,
                      COALESCE(a.total_qty_outbound, 0) AS total_qty_outbound
                    FROM wms_events e
                    LEFT JOIN (
                      SELECT
                        event_id,
                        COUNT(*) AS lines_count,
                        COALESCE(SUM(qty_outbound), 0) AS total_qty_outbound
                      FROM outbound_event_lines
                      GROUP BY event_id
                    ) a
                      ON a.event_id = e.id
                    WHERE e.id = :event_id
                      AND e.event_type = 'OUTBOUND'
                    LIMIT 1
                    """
                ),
                {"event_id": int(event_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(f"outbound_summary_event_not_found: id={event_id}")
    return row


async def get_outbound_summary_lines(
    session: AsyncSession,
    *,
    event_id: int,
) -> List[Dict[str, Any]]:
    rows = (
        (
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
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]
