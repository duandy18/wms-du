"""order_items add fks + index (final & robust)

Revision ID: 463565ce21db
Revises: d824fa2ef8c8
Create Date: 2025-10-29 16:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "463565ce21db"
down_revision = "d824fa2ef8c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    升级要点：
    - 仅在目标表存在时才创建外键（orders/items），避免 UndefinedTable；
    - 索引用 IF NOT EXISTS 保持幂等；
    - 若更早版本已经创建相同外键/索引，则自动跳过。
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # 兜底：如果 order_items 尚不存在，这里不建表（由更早迁移负责）；只做加固
    if not insp.has_table("order_items"):
        return

    # 复合索引兜底（如果前一版没建到，这里再补一次）
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_order_items_order_item "
            "ON public.order_items (order_id, item_id)"
        )
    )

    # 仅在目标表存在时创建外键；避免 UndefinedTable
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
    - 不依赖固定外键名：枚举 order_items 的全部外键逐个删除（幂等）；
    - 索引使用 IF EXISTS 删除，兜住历史命名差异。
    """
    conn = op.get_bind()

    # 删除全部外键（先删指向 orders/items 的；随后兜底删除剩余）
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
              -- 兜底：若还有其它目标表的 FK，一并移除
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

    # 索引幂等删除
    for ix in (
        "ix_order_items_order_item",
        "ix_order_items_order_id",
        "ix_order_items_item_id",
    ):
        conn.execute(sa.text(f"DROP INDEX IF EXISTS public.{ix}"))
