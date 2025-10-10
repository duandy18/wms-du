"""add stock_snapshots table

Revision ID: 1f9e5c2b8a11
Revises: 1088800f816e
Create Date: 2025-10-08 10:12:00
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "1f9e5c2b8a11"
down_revision = "1088800f816e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stock_snapshots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("warehouse_id", sa.Integer, sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("batch_id", sa.Integer, sa.ForeignKey("batches.id"), nullable=True),
        sa.Column("qty_on_hand", sa.Integer, nullable=False, server_default="0"),
        sa.Column("qty_allocated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("qty_available", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("age_days", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "snapshot_date",
            "warehouse_id",
            "location_id",
            "item_id",
            "batch_id",
            name="uq_stock_snapshot_grain",
        ),
    )
    op.create_index("ix_snapshot_date", "stock_snapshots", ["snapshot_date"])
    op.create_index("ix_snapshot_item_date", "stock_snapshots", ["item_id", "snapshot_date"])
    op.create_index("ix_snapshot_wh_date", "stock_snapshots", ["warehouse_id", "snapshot_date"])
    op.create_index("ix_snapshot_expiry_date", "stock_snapshots", ["expiry_date", "snapshot_date"])


def downgrade():
    op.drop_index("ix_snapshot_expiry_date", table_name="stock_snapshots")
    op.drop_index("ix_snapshot_wh_date", table_name="stock_snapshots")
    op.drop_index("ix_snapshot_item_date", table_name="stock_snapshots")
    op.drop_index("ix_snapshot_date", table_name="stock_snapshots")
    op.drop_table("stock_snapshots")
