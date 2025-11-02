"""order_items add foreign keys and index

Revision ID: d824fa2ef8c8
Revises: cfb24bbca2a0
Create Date: 2025-10-29 15:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d824fa2ef8c8"
down_revision = "cfb24bbca2a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 幂等创建复合索引（PG 支持 IF NOT EXISTS）
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_order_items_order_item "
            "ON order_items (order_id, item_id)"
        )
    )

    # 幂等创建外键（存在即跳过）
    conn = op.get_bind()
    fk_names = [
        r[0]
        for r in conn.execute(
            sa.text(
                """
                SELECT conname
                  FROM pg_constraint
                 WHERE conrelid = 'order_items'::regclass
                """
            )
        ).fetchall()
    ]

    if "fk_order_items_order" not in fk_names:
        op.create_foreign_key(
            "fk_order_items_order",
            "order_items",
            "orders",
            ["order_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if "fk_order_items_item" not in fk_names:
        op.create_foreign_key(
            "fk_order_items_item",
            "order_items",
            "items",
            ["item_id"],
            ["id"],
        )


def downgrade() -> None:
    """幂等降级：动态删除外键与索引，不依赖固定名称"""

    conn = op.get_bind()

    # 1) 先删指向 items/orders 的所有外键（枚举名称后逐个删除）
    conn.execute(
        sa.text(
            """
            DO $$
            DECLARE r RECORD;
            BEGIN
              FOR r IN
                SELECT c.conname
                  FROM pg_constraint c
                 WHERE c.contype = 'f'
                   AND c.conrelid = 'order_items'::regclass
                   AND c.confrelid IN ('items'::regclass, 'orders'::regclass)
              LOOP
                EXECUTE format('ALTER TABLE order_items DROP CONSTRAINT %I', r.conname);
              END LOOP;
            END$$;
            """
        )
    )

    # 2) 再删可能存在的索引（不同历史命名一并兜住）
    for ix in (
        "ix_order_items_order_item",
        "ix_order_items_order_id",
        "ix_order_items_item_id",
    ):
        conn.execute(sa.text(f"DROP INDEX IF EXISTS public.{ix}"))
