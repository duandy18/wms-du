"""v_scan_trace: relax join to tolerate ref variants (prefix match)

Revision ID: 20251101_v_scan_trace_relaxed_join
Revises: 13caaa2af6ea
Create Date: 2025-11-02 00:10:00
"""
from alembic import op

revision = "20251101_v_scan_trace_relaxed_join"
down_revision = "13caaa2af6ea"
branch_labels = None
depends_on = None

VIEW_SQL = r"""
CREATE OR REPLACE VIEW v_scan_trace AS
WITH e AS (
  SELECT
    el.id AS event_id,
    el.occurred_at,
    el.source,
    COALESCE(el.meta->>'ref', el.message) AS scan_ref,
    el.meta->>'device_id'            AS device_id,
    el.meta->'context'->>'operator'  AS operator,
    el.meta->'input'->>'mode'        AS mode,
    el.meta->'input'->>'barcode'     AS barcode,
    el.meta->'input'                 AS input_json,
    el.meta->'result'                AS output_json
  FROM event_log el
  WHERE el.source LIKE 'scan_%'
),
l AS (
  SELECT
    sl.id               AS ledger_id,
    sl.ref              AS raw_ref,
    sl.ref_line,
    sl.reason,
    sl.delta,
    sl.after_qty,
    sl.item_id,
    s.location_id       AS location_id,
    COALESCE(loc.warehouse_id, s.warehouse_id) AS warehouse_id,
    COALESCE(s.batch_id, b.id)  AS batch_id,
    COALESCE(s.batch_code, b.batch_code) AS batch_code,
    sl.occurred_at      AS ledger_occurred_at
  FROM stock_ledger sl
  LEFT JOIN stocks    s   ON s.id = sl.stock_id
  LEFT JOIN locations loc ON loc.id = s.location_id
  LEFT JOIN batches   b   ON b.id = s.batch_id
  WHERE sl.ref LIKE 'scan:%'
)
SELECT
  e.scan_ref,
  e.event_id, e.occurred_at, e.source, e.device_id, e.operator, e.mode, e.barcode,
  e.input_json, e.output_json,
  l.ledger_id, l.ref_line, l.reason, l.delta, l.after_qty,
  l.item_id, l.warehouse_id, l.location_id, l.batch_id, l.batch_code, l.ledger_occurred_at
FROM e
LEFT JOIN l
  ON l.raw_ref LIKE e.scan_ref || '%'
ORDER BY e.occurred_at, l.ref_line NULLS FIRST;
"""

DROP_SQL = "DROP VIEW IF EXISTS v_scan_trace;"

def upgrade():
    op.execute(VIEW_SQL)

def downgrade():
    op.execute(DROP_SQL)
