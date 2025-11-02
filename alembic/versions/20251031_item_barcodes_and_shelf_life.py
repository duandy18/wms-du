"""items.shelf_life_days + item_barcodes mapping

Revision ID: 20251031_item_barcodes_and_shelf_life
Revises: 20251031_fix_snapshot_unique_by_item_loc
Create Date: 2025-10-31

说明：
- 为 items 增加 shelf_life_days（保质期，单位：天）
- 新建 item_barcodes（条码 → item 映射），唯一约束 barcode，索引 item_id
- 兼容 Postgres，带 downgrade
"""

from alembic import op
import sqlalchemy as sa


# ----- Alembic identifiers -----
revision = "20251031_item_barcodes_and_shelf_life"
down_revision = "20251031_fix_snapshot_unique_by_item_loc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) items.shelf_life_days
    with op.batch_alter_table("items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("shelf_life_days", sa.Integer(), nullable=True))

    # 给历史数据一个确定值（未知用 0；也可以选择保留 NULL，按你项目口径）
    op.execute("UPDATE items SET shelf_life_days = COALESCE(shelf_life_days, 0)")

    # 2) item_barcodes 映射表
    op.create_table(
        "item_barcodes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "item_id",
            sa.BigInteger(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("barcode", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'EAN13'"),
            comment="EAN13 / UPC / INNER / CUSTOM ...",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("barcode", name="uq_item_barcodes_barcode"),
    )

    op.create_index(
        "ix_item_barcodes_item_id", "item_barcodes", ["item_id"], unique=False
    )


def downgrade() -> None:
    # 先撤索引与表
    op.drop_index("ix_item_barcodes_item_id", table_name="item_barcodes")
    op.drop_table("item_barcodes")

    # 再撤列
    with op.batch_alter_table("items", schema=None) as batch_op:
        batch_op.drop_column("shelf_life_days")
