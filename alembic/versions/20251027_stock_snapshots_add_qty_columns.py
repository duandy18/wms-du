"""stock_snapshots: add qty_on_hand/qty_available + unique(snapshot_date,item_id)

Revision ID: 20251027_stock_snapshots_add_qty_columns
Revises: 20251027_drop_uq_batches_composite
Create Date: 2025-10-27 23:30:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251027_stock_snapshots_add_qty_columns"
down_revision = "20251027_drop_uq_batches_composite"
branch_labels = None
depends_on = None

TABLE = "stock_snapshots"
UQ = "uq_stock_snapshots_day_item"

def _col_absent(conn, table, col):
    sql = sa.text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t AND column_name=:c
        LIMIT 1
    """)
    return conn.execute(sql, {"t": table, "c": col}).scalar() is None

def _constraint_absent(conn, table, name):
    sql = sa.text("""
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid
        WHERE t.relname=:t AND c.conname=:n
        LIMIT 1
    """)
    return conn.execute(sql, {"t": table, "n": name}).scalar() is None

def upgrade():
    conn = op.get_bind()

    # 1) 两个列：qty_on_hand / qty_available（int not null default 0）
    if _col_absent(conn, TABLE, "qty_on_hand"):
        op.add_column(TABLE, sa.Column("qty_on_hand", sa.Integer(), nullable=False, server_default="0"))
        # 去掉默认值（仅用于回填阶段，保持 DDL 干净）
        op.alter_column(TABLE, "qty_on_hand", server_default=None)

    if _col_absent(conn, TABLE, "qty_available"):
        op.add_column(TABLE, sa.Column("qty_available", sa.Integer(), nullable=False, server_default="0"))
        op.alter_column(TABLE, "qty_available", server_default=None)

    # 2) 唯一约束：snapshot_date + item_id
    if _constraint_absent(conn, TABLE, UQ):
        # 若历史上存在相同语义的索引/约束，请按需先 drop 再建
        op.create_unique_constraint(UQ, TABLE, ["snapshot_date", "item_id"])

def downgrade():
    conn = op.get_bind()
    # 回滚唯一约束
    if not _constraint_absent(conn, TABLE, UQ):
        op.drop_constraint(UQ, table_name=TABLE, type_="unique")
    # 回滚列（可选）
    if not _col_absent(conn, TABLE, "qty_available"):
        op.drop_column(TABLE, "qty_available")
    if not _col_absent(conn, TABLE, "qty_on_hand"):
        op.drop_column(TABLE, "qty_on_hand")
