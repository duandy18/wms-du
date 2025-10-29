"""create order_items

Revision ID: cfb24bbca2a0
Revises: 20251029_merge_heads_lockA_single_head
Create Date: 2025-10-29 13:41:26.199993
"""
from alembic import op
import sqlalchemy as sa

# 维持你现在的 head / parent，不改动历史链
revision = "cfb24bbca2a0"
down_revision = "20251029_lockA_finalize_schema"  # 或者你库里真正的唯一 head（如 20251029_merge_heads_lockA_single_head）
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        # 如果你的模型还有其它字段，按需添加：
        # sa.Column("price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_items_order", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_order_items_item")
    )
    op.create_index("ix_order_items_order_item", "order_items", ["order_id", "item_id"], unique=False)

def downgrade():
    op.drop_index("ix_order_items_order_item", table_name="order_items")
    op.drop_table("order_items")
