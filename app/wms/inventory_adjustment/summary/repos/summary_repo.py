from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


SUMMARY_CTE = """
WITH ledger_stats AS (
  SELECT
    event_id,
    COUNT(*)::int AS ledger_row_count,
    COALESCE(SUM(delta), 0)::int AS delta_total,
    COALESCE(SUM(ABS(delta)), 0)::int AS abs_delta_total,
    MIN(reason)::text AS ledger_reason,
    MIN(reason_canon)::text AS ledger_reason_canon,
    CASE
      WHEN COUNT(DISTINCT sub_reason) = 1 THEN MIN(sub_reason)::text
      WHEN COUNT(DISTINCT sub_reason) > 1 THEN 'MIXED'
      ELSE NULL::text
    END AS ledger_sub_reason,
    COUNT(*) FILTER (WHERE sub_reason = 'COUNT_ADJUST')::int AS count_adjust_count,
    COUNT(*) FILTER (WHERE sub_reason = 'COUNT_CONFIRM')::int AS count_confirm_count
  FROM stock_ledger
  WHERE event_id IS NOT NULL
  GROUP BY event_id
),
count_stats AS (
  SELECT
    doc_id,
    COUNT(*)::int AS line_count,
    COALESCE(SUM(COALESCE(diff_qty_base, 0)), 0)::int AS doc_diff_total
  FROM count_doc_lines
  GROUP BY doc_id
),
count_rows AS (
  SELECT
    'COUNT'::text AS adjustment_type,
    d.id::int AS object_id,
    d.count_no::text AS object_no,
    d.warehouse_id::int AS warehouse_id,
    d.status::text AS status,
    COALESCE(e.source_type, 'MANUAL_COUNT')::text AS source_type,
    d.count_no::text AS source_ref,
    e.event_type::text AS event_type,
    e.event_kind::text AS event_kind,
    e.target_event_id::int AS target_event_id,
    COALESCE(e.occurred_at, d.snapshot_at) AS occurred_at,
    COALESCE(e.committed_at, d.posted_at) AS committed_at,
    d.created_at AS created_at,
    COALESCE(cs.line_count, 0)::int AS line_count,
    COALESCE(ls.delta_total, cs.doc_diff_total, 0)::int AS qty_total,
    COALESCE(ls.ledger_row_count, 0)::int AS ledger_row_count,
    ls.ledger_reason::text AS ledger_reason,
    ls.ledger_reason_canon::text AS ledger_reason_canon,
    ls.ledger_sub_reason::text AS ledger_sub_reason,
    COALESCE(ls.delta_total, 0)::int AS delta_total,
    COALESCE(ls.abs_delta_total, ABS(COALESCE(cs.doc_diff_total, 0)))::int AS abs_delta_total,
    CASE
      WHEN d.status <> 'POSTED' THEN 'PENDING'
      WHEN COALESCE(ls.delta_total, 0) > 0 THEN 'INCREASE'
      WHEN COALESCE(ls.delta_total, 0) < 0 THEN 'DECREASE'
      ELSE 'CONFIRM'
    END::text AS direction,
    CASE
      WHEN d.status <> 'POSTED' THEN '盘点单'
      WHEN COALESCE(ls.count_adjust_count, 0) > 0 THEN '盘点调整'
      ELSE '盘点确认'
    END::text AS action_title,
    CASE
      WHEN d.status = 'VOIDED' THEN '盘点单，已作废，' || COALESCE(cs.line_count, 0)::text || ' 行'
      WHEN d.status = 'FROZEN' THEN '盘点单，已冻结，' || COALESCE(cs.line_count, 0)::text || ' 行'
      WHEN d.status = 'COUNTED' THEN '盘点单，已盘点，' || COALESCE(cs.line_count, 0)::text || ' 行'
      WHEN d.status <> 'POSTED' THEN '盘点单，未过账，' || COALESCE(cs.line_count, 0)::text || ' 行'
      WHEN COALESCE(ls.count_adjust_count, 0) > 0 AND COALESCE(ls.delta_total, 0) > 0
        THEN '盘点调整，库存增加 ' || COALESCE(ls.abs_delta_total, 0)::text
      WHEN COALESCE(ls.count_adjust_count, 0) > 0 AND COALESCE(ls.delta_total, 0) < 0
        THEN '盘点调整，库存减少 ' || COALESCE(ls.abs_delta_total, 0)::text
      WHEN COALESCE(ls.count_adjust_count, 0) > 0
        THEN '盘点调整，净变动 0'
      ELSE '盘点确认，无差异'
    END::text AS action_summary,
    d.remark::text AS remark,
    '/inventory-adjustment/count'::text AS detail_route,
    COALESCE(e.committed_at, d.posted_at, d.counted_at, d.snapshot_at, d.created_at) AS sort_at
  FROM count_docs d
  LEFT JOIN wms_events e
    ON e.id = d.posted_event_id
  LEFT JOIN ledger_stats ls
    ON ls.event_id = e.id
  LEFT JOIN count_stats cs
    ON cs.doc_id = d.id
),
inbound_reversal_rows AS (
  SELECT
    'INBOUND_REVERSAL'::text AS adjustment_type,
    e.id::int AS object_id,
    e.event_no::text AS object_no,
    e.warehouse_id::int AS warehouse_id,
    e.status::text AS status,
    e.source_type::text AS source_type,
    e.source_ref::text AS source_ref,
    e.event_type::text AS event_type,
    e.event_kind::text AS event_kind,
    e.target_event_id::int AS target_event_id,
    e.occurred_at AS occurred_at,
    e.committed_at AS committed_at,
    e.created_at AS created_at,
    COALESCE(COUNT(l.id), 0)::int AS line_count,
    COALESCE(ls.delta_total, -COALESCE(SUM(l.qty_base), 0), 0)::int AS qty_total,
    COALESCE(ls.ledger_row_count, 0)::int AS ledger_row_count,
    ls.ledger_reason::text AS ledger_reason,
    ls.ledger_reason_canon::text AS ledger_reason_canon,
    ls.ledger_sub_reason::text AS ledger_sub_reason,
    COALESCE(ls.delta_total, -COALESCE(SUM(l.qty_base), 0), 0)::int AS delta_total,
    COALESCE(ls.abs_delta_total, COALESCE(SUM(l.qty_base), 0), 0)::int AS abs_delta_total,
    'DECREASE'::text AS direction,
    '入库冲回'::text AS action_title,
    (
      CASE e.source_type
        WHEN 'PURCHASE_ORDER' THEN '采购入库'
        WHEN 'MANUAL' THEN '手动入库'
        WHEN 'RETURN' THEN '退货入库'
        ELSE COALESCE(e.source_type, '入库')
      END
      || '，冲回 '
      || COALESCE(ls.abs_delta_total, COALESCE(SUM(l.qty_base), 0), 0)::text
    )::text AS action_summary,
    e.remark::text AS remark,
    ('/inventory-adjustment/inbound-reversal?event_id=' || e.id::text)::text AS detail_route,
    COALESCE(e.committed_at, e.occurred_at, e.created_at) AS sort_at
  FROM wms_events e
  LEFT JOIN inbound_event_lines l
    ON l.event_id = e.id
  LEFT JOIN ledger_stats ls
    ON ls.event_id = e.id
  WHERE e.event_type = 'INBOUND'
    AND e.event_kind = 'REVERSAL'
  GROUP BY
    e.id,
    e.event_no,
    e.warehouse_id,
    e.status,
    e.source_type,
    e.source_ref,
    e.event_type,
    e.event_kind,
    e.target_event_id,
    e.occurred_at,
    e.committed_at,
    e.created_at,
    e.remark,
    ls.ledger_row_count,
    ls.ledger_reason,
    ls.ledger_reason_canon,
    ls.ledger_sub_reason,
    ls.delta_total,
    ls.abs_delta_total
),
outbound_reversal_rows AS (
  SELECT
    'OUTBOUND_REVERSAL'::text AS adjustment_type,
    e.id::int AS object_id,
    e.event_no::text AS object_no,
    e.warehouse_id::int AS warehouse_id,
    e.status::text AS status,
    e.source_type::text AS source_type,
    e.source_ref::text AS source_ref,
    e.event_type::text AS event_type,
    e.event_kind::text AS event_kind,
    e.target_event_id::int AS target_event_id,
    e.occurred_at AS occurred_at,
    e.committed_at AS committed_at,
    e.created_at AS created_at,
    COALESCE(COUNT(l.id), 0)::int AS line_count,
    COALESCE(ls.delta_total, COALESCE(SUM(l.qty_outbound), 0), 0)::int AS qty_total,
    COALESCE(ls.ledger_row_count, 0)::int AS ledger_row_count,
    ls.ledger_reason::text AS ledger_reason,
    ls.ledger_reason_canon::text AS ledger_reason_canon,
    ls.ledger_sub_reason::text AS ledger_sub_reason,
    COALESCE(ls.delta_total, COALESCE(SUM(l.qty_outbound), 0), 0)::int AS delta_total,
    COALESCE(ls.abs_delta_total, COALESCE(SUM(l.qty_outbound), 0), 0)::int AS abs_delta_total,
    'INCREASE'::text AS direction,
    '出库冲回'::text AS action_title,
    (
      CASE e.source_type
        WHEN 'ORDER' THEN '订单出库'
        WHEN 'MANUAL' THEN '手动出库'
        ELSE COALESCE(e.source_type, '出库')
      END
      || '，补回 '
      || COALESCE(ls.abs_delta_total, COALESCE(SUM(l.qty_outbound), 0), 0)::text
    )::text AS action_summary,
    e.remark::text AS remark,
    ('/inventory-adjustment/outbound-reversal?event_id=' || e.id::text)::text AS detail_route,
    COALESCE(e.committed_at, e.occurred_at, e.created_at) AS sort_at
  FROM wms_events e
  LEFT JOIN outbound_event_lines l
    ON l.event_id = e.id
  LEFT JOIN ledger_stats ls
    ON ls.event_id = e.id
  WHERE e.event_type = 'OUTBOUND'
    AND e.event_kind = 'REVERSAL'
  GROUP BY
    e.id,
    e.event_no,
    e.warehouse_id,
    e.status,
    e.source_type,
    e.source_ref,
    e.event_type,
    e.event_kind,
    e.target_event_id,
    e.occurred_at,
    e.committed_at,
    e.created_at,
    e.remark,
    ls.ledger_row_count,
    ls.ledger_reason,
    ls.ledger_reason_canon,
    ls.ledger_sub_reason,
    ls.delta_total,
    ls.abs_delta_total
),
unioned AS (
  SELECT * FROM count_rows
  UNION ALL
  SELECT * FROM inbound_reversal_rows
  UNION ALL
  SELECT * FROM outbound_reversal_rows
)
"""


def _build_where(
    *,
    adjustment_type: str | None,
    warehouse_id: int | None,
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if adjustment_type is not None:
        clauses.append("adjustment_type = :adjustment_type")
        params["adjustment_type"] = str(adjustment_type).strip().upper()

    if warehouse_id is not None:
        clauses.append("warehouse_id = :warehouse_id")
        params["warehouse_id"] = int(warehouse_id)

    if not clauses:
        return "", params

    return "WHERE " + " AND ".join(clauses), params


async def list_inventory_adjustment_summary_rows(
    session: AsyncSession,
    *,
    adjustment_type: str | None,
    warehouse_id: int | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    where_sql, params = _build_where(
        adjustment_type=adjustment_type,
        warehouse_id=warehouse_id,
    )

    count_sql = text(
        f"""
        {SUMMARY_CTE}
        SELECT COUNT(*)
        FROM unioned
        {where_sql}
        """
    )
    total = int((await session.execute(count_sql, params)).scalar_one() or 0)

    list_params = {
        **params,
        "limit": int(limit),
        "offset": int(offset),
    }
    list_sql = text(
        f"""
        {SUMMARY_CTE}
        SELECT
          adjustment_type,
          object_id,
          object_no,
          warehouse_id,
          status,
          source_type,
          source_ref,
          event_type,
          event_kind,
          target_event_id,
          occurred_at,
          committed_at,
          created_at,
          line_count,
          qty_total,
          ledger_row_count,
          ledger_reason,
          ledger_reason_canon,
          ledger_sub_reason,
          delta_total,
          abs_delta_total,
          direction,
          action_title,
          action_summary,
          remark,
          detail_route
        FROM unioned
        {where_sql}
        ORDER BY sort_at DESC NULLS LAST, created_at DESC, object_id DESC
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (await session.execute(list_sql, list_params)).mappings().all()
    return total, [dict(r) for r in rows]



async def get_inventory_adjustment_summary_row(
    session: AsyncSession,
    *,
    adjustment_type: str,
    object_id: int,
) -> dict[str, Any] | None:
    sql = text(
        f"""
        {SUMMARY_CTE}
        SELECT
          adjustment_type,
          object_id,
          object_no,
          warehouse_id,
          status,
          source_type,
          source_ref,
          event_type,
          event_kind,
          target_event_id,
          occurred_at,
          committed_at,
          created_at,
          line_count,
          qty_total,
          ledger_row_count,
          ledger_reason,
          ledger_reason_canon,
          ledger_sub_reason,
          delta_total,
          abs_delta_total,
          direction,
          action_title,
          action_summary,
          remark,
          detail_route
        FROM unioned
        WHERE adjustment_type = :adjustment_type
          AND object_id = :object_id
        LIMIT 1
        """
    )
    row = (
        await session.execute(
            sql,
            {
                "adjustment_type": str(adjustment_type).strip().upper(),
                "object_id": int(object_id),
            },
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_inventory_adjustment_summary_ledger_rows(
    session: AsyncSession,
    *,
    adjustment_type: str,
    object_id: int,
) -> list[dict[str, Any]]:
    sql = text(
        """
        WITH target_event AS (
          SELECT
            CASE
              WHEN :adjustment_type = 'COUNT' THEN (
                SELECT posted_event_id
                FROM count_docs
                WHERE id = :object_id
                LIMIT 1
              )
              ELSE :object_id
            END::int AS event_id
        )
        SELECT
          l.id,
          l.event_id,
          l.ref,
          l.ref_line,
          l.trace_id,
          l.warehouse_id,
          l.item_id,
          i.name AS item_name,
          l.lot_id,
          lo.lot_code,
          iu.id AS base_item_uom_id,
          COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS base_uom_name,
          l.reason,
          l.reason_canon,
          l.sub_reason,
          l.delta,
          l.after_qty,
          l.occurred_at,
          l.created_at
        FROM target_event t
        JOIN stock_ledger l
          ON l.event_id = t.event_id
        LEFT JOIN items i
          ON i.id = l.item_id
        LEFT JOIN item_uoms iu
          ON iu.item_id = l.item_id
         AND iu.is_base IS TRUE
        LEFT JOIN lots lo
          ON lo.id = l.lot_id
        ORDER BY l.ref_line ASC, l.id ASC
        """
    )
    rows = (
        await session.execute(
            sql,
            {
                "adjustment_type": str(adjustment_type).strip().upper(),
                "object_id": int(object_id),
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]


__all__ = [
    "list_inventory_adjustment_summary_rows",
    "get_inventory_adjustment_summary_row",
    "list_inventory_adjustment_summary_ledger_rows",
]
