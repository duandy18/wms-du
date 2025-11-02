"""order_items add foreign keys and index (robust & idempotent)

Revision ID: d824fa2ef8c8
Revises: cfb24bbca2a0
Create Date: 2025-10-29 15:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d824fa2ef8c8"
down_revision = "cfb24bbca2a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    升级要点：
    - 若 order_items 表尚未创建，则补建最小形态（幂等）；
    - 复合索引采用 IF NOT EXISTS；
    - 外键创建前先判断目标表是否存在（orders/items），并且避免重复创建。
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # 0) 若缺表则补建最小形态（与更早迁移兼容）
    if not insp.has_table("order_items"):
        op.create_table(
            "order_items",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("order_id", sa.BigInteger, nullable=False),
            sa.Column("item_id", sa.BigInteger, nullable=False),
            sa.Column("qty", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")),
        )
        # 去掉临时默认
        op.alter_column("order_items", "qty", server_default=None)

    # 1) 复合索引兜底（幂等）
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_order_items_order_item "
            "ON public.order_items (order_id, item_id)"
        )
    )

    # 2) 仅在目标表存在时创建外键；并避免重复创建
    has_orders = insp.has_table("orders")
    has_items = insp.has_table("items")

    existing_fks = [
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'order_items'::regclass AND contype='f'"
            )
        ).fetchall()
    ]

    if has_orders and "fk_order_items_order" not in existing_fks:
        op.create_foreign_key(
            "fk_order_items_order",
            "order_items",
            "orders",
            ["order_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if has_items and "fk_order_items_item" not in existing_fks:
        op.create_foreign_key(
            "fk_order_items_item",
            "order_items",
            "items",
            ["item_id"],
            ["id"],
        )


def downgrade() -> None:
    """
    降级要点：
    - 不依赖固定外键名：枚举 order_items 上所有外键逐个删除（安全、幂等）；
    - 索引用 DROP INDEX IF EXISTS（兜住历史命名差异）。
    """
    conn = op.get_bind()

    # 1) 删除所有外键（先删指向 items/orders 的，随后兜底再删其余外键，避免历史漂移）
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
    # 兜底：若还有其它目标表的 FK，也一并清掉（避免历史差异）
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
              LOOP
                EXECUTE format('ALTER TABLE order_items DROP CONSTRAINT %I', r.conname);
              END LOOP;
            END$$;
            """
        )
    )

    # 2) 幂等删除可能存在的索引命名（覆盖常见命名）
    for ix in (
        "ix_order_items_order_item",
        "ix_order_items_order_id",
        "ix_order_items_item_id",
    ):
        conn.execute(sa.text(f"DROP INDEX IF EXISTS public.{ix}"))
