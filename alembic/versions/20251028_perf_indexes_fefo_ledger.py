"""perf indexes for fefo(batches) & ledger timeline

Revision ID: 20251028_perf_indexes_fefo_ledger
Revises: 20251028_stock_ledger_add_item_id
Create Date: 2025-10-28 12:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20251028_perf_indexes_fefo_ledger"
down_revision = "20251028_stock_ledger_add_item_id"
branch_labels = None
depends_on = None


def _idx_exists(conn, name):
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n LIMIT 1"),
            {"n": name},
        ).scalar()
    )


def upgrade():
    conn = op.get_bind()
    # FEFO 扫描：item+loc+expiry+id
    if not _idx_exists(conn, "ix_batches_fefo"):
        op.execute(
            "CREATE INDEX ix_batches_fefo ON batches (item_id, location_id, expiry_date, id)"
        )
    # Ledger 时间线：stock 维度
    if not _idx_exists(conn, "ix_stock_ledger_stock_time"):
        op.execute(
            "CREATE INDEX ix_stock_ledger_stock_time ON stock_ledger (stock_id, occurred_at)"
        )


def downgrade():
    conn = op.get_bind()
    if _idx_exists(conn, "ix_stock_ledger_stock_time"):
        op.execute("DROP INDEX ix_stock_ledger_stock_time")
    if _idx_exists(conn, "ix_batches_fefo"):
        op.execute("DROP INDEX ix_batches_fefo")
