# alembic/versions/xxxx_add_constraints_to_stocks.py

from alembic import op

# revision identifiers, used by Alembic.
revision = "xxxx_add_constraints_to_stocks"
down_revision = "<填入上一版本号>"  # ← 这里填你真实的上一个 revision id
branch_labels = None
depends_on = None


def upgrade():
    # 唯一约束：同一 item+location 仅一行
    op.create_unique_constraint(
        "uq_stocks_item_location",
        "stocks",
        ["item_id", "location_id"],
    )
    # 检查约束：不允许负库存（SQLite 对 CHECK 支持简单表达式）
    try:
        op.create_check_constraint(
            "ck_stocks_non_negative",
            "stocks",
            "quantity >= 0",
        )
    except Exception:
        pass
    # 常用查询索引
    op.create_index("ix_stocks_item", "stocks", ["item_id"])
    op.create_index("ix_stocks_location", "stocks", ["location_id"])


def downgrade():
    try:
        op.drop_index("ix_stocks_location", table_name="stocks")
    except Exception:
        pass
    try:
        op.drop_index("ix_stocks_item", table_name="stocks")
    except Exception:
        pass
    try:
        op.drop_constraint("ck_stocks_non_negative", "stocks", type_="check")
    except Exception:
        pass
    try:
        op.drop_constraint("uq_stocks_item_location", "stocks", type_="unique")
    except Exception:
        pass
