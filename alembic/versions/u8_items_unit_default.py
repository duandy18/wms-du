"""set default 'PCS' for items.unit and backfill nulls

Revision ID: u8_items_unit_default
Revises: u7_fix_ledger_ref_line_default
Create Date: 2025-10-22
"""
from alembic import op
import sqlalchemy as sa

revision = "u8_items_unit_default"
down_revision = "u7_fix_ledger_ref_line_default"
branch_labels = None
depends_on = None

def upgrade():
    # 1) 先回填历史 NULL（若有）
    op.execute("UPDATE items SET unit = 'PCS' WHERE unit IS NULL")
    # 2) 设置默认值
    op.execute("ALTER TABLE items ALTER COLUMN unit SET DEFAULT 'PCS'")
    # 3) 保持 NOT NULL（如果之前不是 NOT NULL，可在此设为 NOT NULL）
    op.execute("ALTER TABLE items ALTER COLUMN unit SET NOT NULL")

def downgrade():
    # 回退默认值（保持 NOT NULL 与否按你需要）
    op.execute("ALTER TABLE items ALTER COLUMN unit DROP DEFAULT")
