"""align order_items FKs and uniqs

Revision ID: 6dcef1580344
Revises: 20251112_drop_unused_indexes_v2
Create Date: 2025-11-09 19:44:41.772323
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6dcef1580344"
down_revision: Union[str, Sequence[str], None] = "20251112_drop_unused_indexes_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table, schema="public")


def _has_fk(bind, table: str, name: str) -> bool:
    sql = sa.text(
        """
        SELECT 1
          FROM information_schema.table_constraints
         WHERE table_schema = 'public'
           AND table_name   = :t
           AND constraint_type = 'FOREIGN KEY'
           AND constraint_name = :n
         LIMIT 1
        """
    )
    return bind.execute(sql, {"t": table, "n": name}).first() is not None


def _has_unique(bind, table: str, name: str) -> bool:
    sql = sa.text(
        """
        SELECT 1
          FROM information_schema.table_constraints
         WHERE table_schema = 'public'
           AND table_name   = :t
           AND constraint_type = 'UNIQUE'
           AND constraint_name = :n
         LIMIT 1
        """
    )
    return bind.execute(sql, {"t": table, "n": name}).first() is not None


def upgrade() -> None:
    bind = op.get_bind()

    # 确保核心表存在：order_items / orders / items
    if not _has_table(bind, "order_items"):
        return
    if not _has_table(bind, "orders"):
        return
    if not _has_table(bind, "items"):
        return

    # 1) 清洗潜在脏数据（避免 FK 创建失败）
    bind.execute(
        sa.text(
            """
    DELETE FROM order_items oi
    WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.id = oi.order_id)
       OR (oi.item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM items i WHERE i.id = oi.item_id))
    """
        )
    )

    # 2) 若历史上有同名外键，先删再建（用元数据检查，避免事务被打坏）
    if _has_fk(bind, "order_items", "fk_order_items_order"):
        op.drop_constraint("fk_order_items_order", "order_items", type_="foreignkey")
    if _has_fk(bind, "order_items", "fk_order_items_item"):
        op.drop_constraint("fk_order_items_item", "order_items", type_="foreignkey")

    # 3) 创建外键（仅在不存在时创建）
    if not _has_fk(bind, "order_items", "fk_order_items_order"):
        op.create_foreign_key(
            "fk_order_items_order",
            "order_items",
            "orders",
            ["order_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if not _has_fk(bind, "order_items", "fk_order_items_item"):
        op.create_foreign_key(
            "fk_order_items_item",
            "order_items",
            "items",
            ["item_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # 4) （可选）唯一性：同一订单同一商品只出现一次
    if not _has_unique(bind, "order_items", "uq_order_items_order_item"):
        op.create_unique_constraint(
            "uq_order_items_order_item",
            "order_items",
            ["order_id", "item_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    # 回滚时按创建的逆序删除（带守卫）
    if _has_unique(bind, "order_items", "uq_order_items_order_item"):
        op.drop_constraint("uq_order_items_order_item", "order_items", type_="unique")

    if _has_fk(bind, "order_items", "fk_order_items_item"):
        op.drop_constraint("fk_order_items_item", "order_items", type_="foreignkey")

    if _has_fk(bind, "order_items", "fk_order_items_order"):
        op.drop_constraint("fk_order_items_order", "order_items", type_="foreignkey")
