# alembic/versions/20251028_stock_snapshots_add_updated_at.py
"""stock_snapshots: add updated_at (idempotent)

Revision ID: 20251028_stock_snapshots_add_updated_at
Revises: 20251028_snapshots_uq_by_wh_loc_item
Create Date: 2025-10-28 16:20:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20251028_stock_snapshots_add_updated_at"
down_revision = "20251028_snapshots_uq_by_wh_loc_item"
branch_labels = None
depends_on = None


def _col_exists(conn, table, col):
    return bool(
        conn.execute(
            sa.text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t AND column_name=:c
        LIMIT 1
    """),
            {"t": table, "c": col},
        ).scalar()
    )


def upgrade():
    conn = op.get_bind()
    if not _col_exists(conn, "stock_snapshots", "updated_at"):
        op.add_column(
            "stock_snapshots", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
        )
    if not _col_exists(conn, "stock_snapshots", "created_at"):
        op.add_column(
            "stock_snapshots", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade():
    conn = op.get_bind()
    if _col_exists(conn, "stock_snapshots", "updated_at"):
        op.drop_column("stock_snapshots", "updated_at")
    # created_at 旧库可能已经被其他模块使用，回滚时谨慎；这里不删
