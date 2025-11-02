"""orders.updated_at: set DEFAULT NOW() and backfill (idempotent)

给 orders.updated_at 设默认值 NOW()，并回填历史 NULL。
避免创建订单时因未显式赋值而触发 NOT NULL 违反。

Revision ID: 20251030_orders_updated_at_default_now
Revises: 20251030_orders_total_amount_default_zero
Create Date: 2025-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20251030_orders_updated_at_default_now"
down_revision = "20251030_orders_total_amount_default_zero"
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
    if not _has_col(conn, "orders", "updated_at"):
        return  # 不强加列，保持幂等

    # 设置默认值
    op.alter_column("orders", "updated_at", server_default=sa.text("NOW()"))
    # 回填历史空值
    conn.exec_driver_sql("UPDATE orders SET updated_at=NOW() WHERE updated_at IS NULL")

def downgrade():
    # 仅移除默认值，不回滚数据
    op.alter_column("orders", "updated_at", server_default=None)
