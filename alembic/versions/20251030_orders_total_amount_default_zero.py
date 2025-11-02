"""orders.total_amount: set DEFAULT 0 and backfill (idempotent)

- 给 orders.total_amount 设置默认值 0（新插入未显式赋值时不再触发 NOT NULL 违反）
- 回填历史 NULL 为 0
- 幂等：若列不存在或已设置默认值，不会报错

Revision ID: 20251030_orders_total_amount_default_zero
Revises: 20251030_orders_add_minimal_columns
Create Date: 2025-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20251030_orders_total_amount_default_zero"
down_revision = "20251030_orders_add_minimal_columns"
branch_labels = None
depends_on = None

def _has_col(conn, table, col) -> bool:
    return bool(conn.exec_driver_sql(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
        """, (table, col)
    ).scalar())

def upgrade():
    conn = op.get_bind()
    if not _has_col(conn, "orders", "total_amount"):
        # 若环境没有该列，则不做处理（保持幂等）
        return

    # 设置默认值 0
    op.alter_column("orders", "total_amount", server_default=sa.text("0"))
    # 回填历史空值
    conn.exec_driver_sql("UPDATE orders SET total_amount=0 WHERE total_amount IS NULL")

def downgrade():
    # 仅移除默认值，不回滚数据
    op.alter_column("orders", "total_amount", server_default=None)
