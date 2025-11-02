"""v_scan_trace: join scan event_log with stock_ledger by scan_ref (use occurred_at)

Revision ID: 20251101_v_scan_trace_view
Revises: 20251101_event_log_occurred_at_unify
Create Date: 2025-11-01 22:15:00
"""
from alembic import op

revision = "20251101_v_scan_trace_view"
down_revision = "20251101_event_log_occurred_at_unify"
branch_labels = None
depends_on = None

VIEW_SQL = r"""
CREATE OR REPLACE VIEW v_scan_trace AS
-- 事件侧：只取扫码来源，时间口径统一为 occurred_at
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
-- 台账侧：通过 stocks 反解 location/warehouse 与 batch 信息
l AS (
  SELECT
    sl.id               AS ledger_id,
    sl.ref              AS scan_ref,
    sl.ref_line,
    sl.reason,
    sl.delta,
    sl.after_qty,
    sl.item_id,
    s.location_id       AS location_id,
    COALESCE(loc.warehouse_id, s.warehouse_id) AS warehouse_id, -- 兼容历史：若 stocks 上带 warehouse_id 列
    COALESCE(s.batch_id, b.id)  AS batch_id,
    COALESCE(s.batch_code, b.batch_code) AS batch_code,
    sl.occurred_at      AS ledger_occurred_at
  FROM stock_ledger sl
  LEFT JOIN stocks    s   ON s.id = sl.stock_id         -- 以 stock_id 链接到库存
  LEFT JOIN locations loc ON loc.id = s.location_id     -- 再由库存反解仓库
  LEFT JOIN batches   b   ON b.id = s.batch_id          -- 需要时补齐批次信息
  WHERE sl.ref LIKE 'scan:%'
)
SELECT
  e.scan_ref,
  e.event_id, e.occurred_at, e.source, e.device_id, e.operator, e.mode, e.barcode,
  e.input_json, e.output_json,
  l.ledger_id, l.ref_line, l.reason, l.delta, l.after_qty,
  l.item_id, l.warehouse_id, l.location_id, l.batch_id, l.batch_code, l.ledger_occurred_at
FROM e
LEFT JOIN l USING (scan_ref)
ORDER BY e.occurred_at, l.ref_line NULLS FIRST;
"""

DROP_SQL = r"DROP VIEW IF EXISTS v_scan_trace;"

def upgrade():
    op.execute(VIEW_SQL)

def downgrade():
    op.execute(DROP_SQL)
