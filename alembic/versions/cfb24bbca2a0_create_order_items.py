"""create order_items (safe)

Revision ID: cfb24bbca2a0
Revises: 20251029_merge_heads_lockA_single_head
Create Date: 2025-10-29 13:41:26.199993
"""
from alembic import op
import sqlalchemy as sa


revision = "cfb24bbca2a0"
down_revision = "20251029_merge_heads_lockA_single_head"
branch_labels = None
depends_on = None


def _has_table(bind, name: str, schema: str | None = None) -> bool:
    insp = sa.inspect(bind)
    return insp.has_table(name, schema=schema)


def upgrade():
    bind = op.get_bind()

    # 1) 父表 items 若不存在，创建“最小结构”
    if not _has_table(bind, "items"):
        op.create_table(
            "items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("sku", sa.String(length=128), nullable=False, unique=True),
            sa.Column("name", sa.String(length=255), nullable=False),
        )

    # 2) 父表 orders 若不存在，创建“最小结构”
    if not _has_table(bind, "orders"):
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    # 3) 子表 order_items（本迁移的目标表）
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_items_order", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_order_items_item"),
    )
    op.create_index("ix_order_items_order_item", "order_items", ["order_id", "item_id"], unique=False)


def downgrade():
    # 仅删除当前迁移创建的对象（不要动父表）
    op.drop_index("ix_order_items_order_item", table_name="order_items")
    op.drop_table("order_items")
