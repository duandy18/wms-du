"""p40_create_stock_snapshots_v2

Revision ID: 5d114a84c638
Revises: 935868364548
Create Date: 2025-11-16 01:08:35.666839
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5d114a84c638"
down_revision: Union[str, Sequence[str], None] = "935868364548"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create stock_snapshots table (v2 schema)."""

    # 防御：如果之前环境中已经有旧版 stock_snapshots，先删掉再按 v2 结构重建。
    # 用在测试 / 开发库是 OK 的；生产库要保留历史的话需要单独做数据迁移。
    op.execute("DROP TABLE IF EXISTS stock_snapshots CASCADE;")

    op.create_table(
        "stock_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "warehouse_id",
            sa.Integer(),
            sa.ForeignKey("warehouses.id"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id"),
            nullable=False,
        ),
        sa.Column("batch_code", sa.String(length=64), nullable=False),
        sa.Column(
            "qty_on_hand",
            sa.Numeric(18, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "qty_allocated",
            sa.Numeric(18, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "qty_available",
            sa.Numeric(18, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.UniqueConstraint(
            "snapshot_date",
            "warehouse_id",
            "item_id",
            "batch_code",
            name="uq_stock_snapshot_grain_v2",
        ),
    )

    op.create_index(
        "ix_stock_snapshots_item_id",
        "stock_snapshots",
        ["item_id"],
    )
    op.create_index(
        "ix_stock_snapshots_snapshot_date",
        "stock_snapshots",
        ["snapshot_date"],
    )
    op.create_index(
        "ix_stock_snapshots_warehouse_id",
        "stock_snapshots",
        ["warehouse_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stock_snapshots_item_id", table_name="stock_snapshots")
    op.drop_index("ix_stock_snapshots_snapshot_date", table_name="stock_snapshots")
    op.drop_index("ix_stock_snapshots_warehouse_id", table_name="stock_snapshots")
    op.drop_table("stock_snapshots")
