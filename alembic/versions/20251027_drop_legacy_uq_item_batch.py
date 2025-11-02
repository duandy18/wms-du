"""drop legacy unique (item_id, batch_code) on batches

Revision ID: 20251027_drop_legacy_uq_item_batch
Revises: 20251027_add_uq_batches_unique
Create Date: 2025-10-27 22:10:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20251027_drop_legacy_uq_item_batch"
down_revision = "20251027_add_uq_batches_unique"
branch_labels = None
depends_on = None

TABLE = "batches"
LEGACY_UQ_NAME = "uq_batches_item_batch"  # 常见旧名，实际也做列匹配兜底

def _find_constraints_on_cols(conn, table, cols):
    sql = sa.text("""
    SELECT c.conname
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE t.relname = :table
      AND c.contype = 'u'
      AND (
        SELECT ARRAY_AGG(att.attname ORDER BY att.attname)
        FROM unnest(c.conkey) AS key(attnum)
        JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = key.attnum
      ) = (
        SELECT ARRAY_AGG(col ORDER BY col)
        FROM unnest(:cols::text[]) AS s(col)
      )
    """)
    return [r[0] for r in conn.execute(sql, {"table": table, "cols": cols}).fetchall()]

def upgrade():
    conn = op.get_bind()

    # 1) 优先按名字删除
    sql_name = sa.text("""
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid
        WHERE t.relname=:t AND c.conname=:n
        LIMIT 1
    """)
    if conn.execute(sql_name, {"t": TABLE, "n": LEGACY_UQ_NAME}).scalar():
        op.drop_constraint(LEGACY_UQ_NAME, table_name=TABLE, type_="unique")
        return

    # 2) 兜底：按列集合 (item_id, batch_code) 查找并删除
    for conname in _find_constraints_on_cols(conn, TABLE, ["item_id", "batch_code"]):
        op.drop_constraint(conname, table_name=TABLE, type_="unique")

def downgrade():
    # 可选：恢复旧唯一约束（通常不需要）
    op.create_unique_constraint(LEGACY_UQ_NAME, TABLE, ["item_id", "batch_code"])
