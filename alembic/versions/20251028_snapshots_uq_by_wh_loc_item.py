"""stock_snapshots: add wh/loc cols (idempotent) + UQ on (snapshot_date, warehouse_id, location_id, item_id)

Revision ID: 20251028_snapshots_uq_by_wh_loc_item
Revises: 20251028_event_error_pending_view
Create Date: 2025-10-28 14:20:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20251028_snapshots_uq_by_wh_loc_item"
down_revision = "20251028_event_error_pending_view"
branch_labels = None
depends_on = None

TABLE = "stock_snapshots"
COL_WH = "warehouse_id"
COL_LOC = "location_id"
UQ_NEW = "uq_stock_snapshot_grain"
IDX_ITEM_DATE = "ix_ss_item_date"
IDX_WH_DATE = "ix_ss_wh_date"

def _col_exists(conn, table, col):
    return bool(conn.execute(sa.text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t AND column_name=:c
        LIMIT 1
    """), {"t": table, "c": col}).scalar())

def _idx_exists(conn, name):
    return bool(conn.execute(sa.text("""
        SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n
        LIMIT 1
    """), {"n": name}).scalar())

def _uq_exists(conn, table, name):
    return bool(conn.execute(sa.text("""
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid
        WHERE t.relname=:t AND c.conname=:n AND c.contype='u' LIMIT 1
    """), {"t": table, "n": name}).scalar())

def upgrade():
    conn = op.get_bind()

    # 1) 先加列（可空，避免对历史数据强制回填）
    if not _col_exists(conn, TABLE, COL_WH):
        op.add_column(TABLE, sa.Column(COL_WH, sa.Integer(), nullable=True))
    if not _col_exists(conn, TABLE, COL_LOC):
        op.add_column(TABLE, sa.Column(COL_LOC, sa.Integer(), nullable=True))

    # 2) 辅助索引（若不存在）
    if not _idx_exists(conn, IDX_ITEM_DATE):
        op.create_index(IDX_ITEM_DATE, TABLE, ["item_id", "snapshot_date"])
    if not _idx_exists(conn, IDX_WH_DATE) and _col_exists(conn, TABLE, COL_WH):
        op.create_index(IDX_WH_DATE, TABLE, [COL_WH, "snapshot_date"])

    # 3) 新唯一键（四列粒度），若已存在则跳过
    if not _uq_exists(conn, TABLE, UQ_NEW):
        op.create_unique_constraint(
            UQ_NEW,
            TABLE,
            ["snapshot_date", COL_WH, COL_LOC, "item_id"],
        )

def downgrade():
    conn = op.get_bind()
    # 回滚唯一键
    if _uq_exists(conn, TABLE, UQ_NEW):
        op.drop_constraint(UQ_NEW, TABLE, type_="unique")
    # 回滚索引
    if _idx_exists(conn, IDX_WH_DATE):
        op.drop_index(IDX_WH_DATE, table_name=TABLE)
    if _idx_exists(conn, IDX_ITEM_DATE):
        op.drop_index(IDX_ITEM_DATE, table_name=TABLE)
    # 可选回滚列（谨慎）：这里只在确实存在时删除
    if _col_exists(conn, TABLE, COL_LOC):
        op.drop_column(TABLE, COL_LOC)
    if _col_exists(conn, TABLE, COL_WH):
        op.drop_column(TABLE, COL_WH)
