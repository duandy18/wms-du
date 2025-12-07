"""align order_items FKs and uniqs

Revision ID: 6dcef1580344
Revises: 20251112_drop_unused_indexes_v2
Create Date: 2025-11-09 19:44:41.772323
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6dcef1580344"
down_revision: Union[str, Sequence[str], None] = "20251112_drop_unused_indexes_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 清洗潜在脏数据（避免 FK 创建失败）
    op.execute("""
    DELETE FROM order_items oi
    WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.id = oi.order_id)
       OR (oi.item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM items i WHERE i.id = oi.item_id))
    """)

    # 2) 若历史上有同名外键，先删再建（容错处理）
    try:
        op.drop_constraint("fk_order_items_order", "order_items", type_="foreignkey")
    except Exception:
        pass
    try:
        op.drop_constraint("fk_order_items_item", "order_items", type_="foreignkey")
    except Exception:
        pass

    # 3) 创建外键
    op.create_foreign_key(
        "fk_order_items_order",
        "order_items",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_order_items_item",
        "order_items",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 4) （可选）唯一性：同一订单同一商品只出现一次
    # 如你的表已有 surrogate 主键 id，可用唯一约束；如无 id，建议复合主键。
    try:
        op.create_unique_constraint(
            "uq_order_items_order_item",
            "order_items",
            ["order_id", "item_id"],
        )
    except Exception:
        # 如果已经存在就跳过
        pass


def downgrade() -> None:
    # 回滚时按创建的逆序删除
    try:
        op.drop_constraint("uq_order_items_order_item", "order_items", type_="unique")
    except Exception:
        pass

    op.drop_constraint("fk_order_items_item", "order_items", type_="foreignkey")
    op.drop_constraint("fk_order_items_order", "order_items", type_="foreignkey")
