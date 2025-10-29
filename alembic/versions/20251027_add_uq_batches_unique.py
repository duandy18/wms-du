"""add unique on batches (item_id, warehouse_id, location_id, batch_code)

Revision ID: 20251027_add_uq_batches_unique
Revises: 20251027_stores_add_platform_credentials
Create Date: 2025-10-27 21:25:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251027_add_uq_batches_unique"
down_revision = "20251027_stores_add_platform_credentials"
branch_labels = None
depends_on = None

UQ_NAME = "uq_batches_item_wh_loc_code"
TABLE = "batches"
COLUMNS = ["item_id", "warehouse_id", "location_id", "batch_code"]

def _constraint_absent(conn, table, name):
    sql = sa.text("""
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = :table AND c.conname = :name
        LIMIT 1
    """)
    return conn.execute(sql, {"table": table, "name": name}).scalar() is None

def _duplicates_count(conn):
    cols = ", ".join(COLUMNS)
    sql = sa.text(f"""
        SELECT COUNT(*) FROM (
          SELECT {cols}, COUNT(*) AS n
          FROM {TABLE}
          GROUP BY {cols}
          HAVING COUNT(*) > 1
        ) d
    """)
    return int(conn.execute(sql).scalar() or 0)

def upgrade():
    conn = op.get_bind()

    # 先检查是否已有此约束
    if not _constraint_absent(conn, TABLE, UQ_NAME):
        return

    # 检查是否存在重复数据，若有则阻止创建（避免迁移卡死）
    dups = _duplicates_count(conn)
    if dups > 0:
        raise RuntimeError(
            f"[{UQ_NAME}] found {dups} duplicate key group(s) in {TABLE}. "
            f"Please de-dup the data before applying the unique constraint."
        )

    # 创建唯一约束
    op.create_unique_constraint(UQ_NAME, TABLE, COLUMNS)

def downgrade():
    conn = op.get_bind()
    if _constraint_absent(conn, TABLE, UQ_NAME):
        return
    op.drop_constraint(UQ_NAME, TABLE, type_="unique")
