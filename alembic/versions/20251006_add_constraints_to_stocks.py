# alembic/versions/20251006_add_constraints_to_stocks.py

from alembic import op

# ——— rev ids ———
revision = "20251006_add_constraints_to_stocks"
down_revision = "f995a82ac74e"
branch_labels = None
depends_on = None


def upgrade():
    """
    SQLite 不支持在线添加约束，这里用 batch 重建表并添加：
    - 唯一约束 uq_stocks_item_location(item_id, location_id)
    - 检查约束 ck_stocks_non_negative(quantity >= 0)（若不需要可删除）
    - 常用索引：ix_stocks_item, ix_stocks_location
    """
    # 用 batch_alter_table 触发 copy-and-move
    with op.batch_alter_table("stocks", recreate="always") as batch_op:
        # 唯一约束（同一 item+location 仅一行）
        batch_op.create_unique_constraint("uq_stocks_item_location", ["item_id", "location_id"])
        # 检查约束（允许你按需保留/删除）
        try:
            batch_op.create_check_constraint("ck_stocks_non_negative", "quantity >= 0")
        except Exception:
            # 一些方言/旧 SQLite 可能报不支持，忽略
            pass

    # 索引放在 batch 外创建（避免重复重建）
    op.create_index("ix_stocks_item", "stocks", ["item_id"], unique=False)
    op.create_index("ix_stocks_location", "stocks", ["location_id"], unique=False)


def downgrade():
    # 回滚：删索引→删检查/唯一约束（在 SQLite 上如果失败同样忽略）
    op.drop_index("ix_stocks_location", table_name="stocks")
    op.drop_index("ix_stocks_item", table_name="stocks")

    # 用 batch 去掉约束（重建表）
    with op.batch_alter_table("stocks", recreate="always") as batch_op:
        try:
            batch_op.drop_constraint("ck_stocks_non_negative", type_="check")
        except Exception:
            pass
        try:
            batch_op.drop_constraint("uq_stocks_item_location", type_="unique")
        except Exception:
            pass
