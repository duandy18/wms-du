"""create order_items (safe)

Revision ID: cfb24bbca2a0
Revises: 20251029_merge_heads_lockA_single_head
Create Date: 2025-10-29 11:40:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "cfb24bbca2a0"
down_revision = "20251029_merge_heads_lockA_single_head"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 若表不存在则创建最小形态（幂等）
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("order_items"):
        op.create_table(
            "order_items",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("order_id", sa.BigInteger, nullable=False),
            sa.Column("item_id", sa.BigInteger, nullable=False),
            sa.Column("qty", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")),
        )
        op.alter_column("order_items", "qty", server_default=None)

    # 复合索引（有些历史路径会在别的迁移里创建，这里用 IF NOT EXISTS 保守兜底）
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_order_items_order_item "
            "ON public.order_items (order_id, item_id)"
        )
    )


def downgrade() -> None:
    """幂等降级：索引按 IF EXISTS 删除，不依赖固定存在的名字。"""
    conn = op.get_bind()

    # 常见命名
    conn.execute(sa.text("DROP INDEX IF EXISTS public.ix_order_items_order_item"))
    # 若历史曾分开建过单列索引，也顺带兜一下（不会报错）
    conn.execute(sa.text("DROP INDEX IF EXISTS public.ix_order_items_order_id"))
    conn.execute(sa.text("DROP INDEX IF EXISTS public.ix_order_items_item_id"))
    # 不在此删除表，保持与后续迁移的删除顺序一致
