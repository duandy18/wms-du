"""scan event views: v_scan_recent / v_scan_ledger_recent (safe recreate, portable)

Revision ID: 20251031_scan_event_views
Revises: 20251031_locations_add_code_and_uq
Create Date: 2025-10-31
"""
from alembic import op

revision = "20251031_scan_event_views"
down_revision = "20251031_locations_add_code_and_uq"
branch_labels = None
depends_on = None

SQL_UP = r"""
-- 为避免列名/列序变更触发 REPLACE 限制，先安全删除再重建
DROP VIEW IF EXISTS v_scan_recent CASCADE;
DROP VIEW IF EXISTS v_scan_ledger_recent CASCADE;

-- 事件巡检（不依赖 occurred_at/created_at）
CREATE VIEW v_scan_recent AS
SELECT
  e.id,
  e.source,
  e.message,
  e.meta->'in'  AS payload_in,
  e.meta->'out' AS payload_out,
  (e.meta->'ctx')->>'warehouse_id' AS warehouse_id,
  (e.meta->'ctx')->>'location_id'  AS location_id,
  (e.meta->'ctx')->>'item_id'      AS item_id,
  (e.meta->'ctx')->>'batch_code'   AS batch_code
FROM event_log e
WHERE e.source LIKE 'scan_%'
ORDER BY e.id DESC;

-- 台账巡检：仅保留跨版本稳定列（不引用 location_id）
CREATE VIEW v_scan_ledger_recent AS
SELECT
  l.id,
  l.item_id,
  l.reason,
  l.ref,
  l.delta,
  l.after_qty
FROM stock_ledger l
WHERE l.ref LIKE 'scan:%'
ORDER BY l.id DESC;
"""

SQL_DOWN = r"""
DROP VIEW IF EXISTS v_scan_ledger_recent CASCADE;
DROP VIEW IF EXISTS v_scan_recent CASCADE;
"""

def upgrade() -> None:
    op.execute(SQL_UP)

def downgrade() -> None:
    op.execute(SQL_DOWN)
