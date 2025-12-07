"""drop_po_phase1_columns

Revision ID: 8ca4bc063929
Revises: adf4ec9eeef8
Create Date: 2025-11-28 15:27:42.591245

彻底删除 purchase_orders 的 Phase 1 遗留字段：
- item_id
- qty_ordered
- qty_received
- unit_cost

并删除旧索引 ix_purchase_orders_wh_item_status 与外键 fk_po_item。
新增简化索引 ix_purchase_orders_wh_status。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8ca4bc063929"
down_revision: Union[str, Sequence[str], None] = "adf4ec9eeef8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 删除旧外键（指向 items.id）
    op.drop_constraint("fk_po_item", "purchase_orders", type_="foreignkey")

    # 2. 删除旧索引（warehouse_id, item_id, status）
    op.drop_index(
        "ix_purchase_orders_wh_item_status",
        table_name="purchase_orders",
    )

    # 3. 删除旧字段
    op.drop_column("purchase_orders", "unit_cost")
    op.drop_column("purchase_orders", "qty_received")
    op.drop_column("purchase_orders", "qty_ordered")
    op.drop_column("purchase_orders", "item_id")

    # 4. 新建简化索引（warehouse_id, status）
    op.create_index(
        "ix_purchase_orders_wh_status",
        "purchase_orders",
        ["warehouse_id", "status"],
    )


def downgrade() -> None:
    # 逆序：删除新索引
    op.drop_index(
        "ix_purchase_orders_wh_status",
        table_name="purchase_orders",
    )

    # 恢复旧列
    op.add_column(
        "purchase_orders",
        sa.Column("item_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "purchase_orders",
        sa.Column("qty_ordered", sa.Integer(), nullable=True),
    )
    op.add_column(
        "purchase_orders",
        sa.Column(
            "qty_received",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "purchase_orders",
        sa.Column(
            "unit_cost",
            sa.Numeric(12, 2),
            nullable=True,
        ),
    )

    # 恢复外键
    op.create_foreign_key(
        "fk_po_item",
        "purchase_orders",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 恢复旧索引
    op.create_index(
        "ix_purchase_orders_wh_item_status",
        "purchase_orders",
        ["warehouse_id", "item_id", "status"],
    )
