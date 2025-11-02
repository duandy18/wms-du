from alembic import op
import sqlalchemy as sa

# 修订信息
revision = "b17d20cf69a3"
down_revision = "20251101_v_scan_trace_relaxed_join"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 新增列（先允许 NULL）
    op.add_column(
        "stock_ledger",
        sa.Column("location_id", sa.Integer(), nullable=True),
    )

    # 2) 用 stock_id 反查 stocks.location_id 回填历史
    conn.execute(sa.text(
        """
        UPDATE stock_ledger l
           SET location_id = s.location_id
          FROM stocks s
         WHERE l.stock_id = s.id
           AND l.location_id IS NULL
        """
    ))

    # 3) 索引（按 location / (location,item) 常用过滤）
    op.create_index("ix_stock_ledger_location_id", "stock_ledger", ["location_id"], unique=False)
    op.create_index("ix_stock_ledger_loc_item", "stock_ledger", ["location_id", "item_id"], unique=False)

    # 4) 如需收紧为 NOT NULL，确认数据后再做二次迁移更稳：
    # conn.execute(sa.text("ALTER TABLE stock_ledger ALTER COLUMN location_id SET NOT NULL"))


def downgrade() -> None:
    # 回滚：先删索引，再删列
    op.drop_index("ix_stock_ledger_loc_item", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_location_id", table_name="stock_ledger")
    op.drop_column("stock_ledger", "location_id")
