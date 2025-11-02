"""orders: ensure minimal columns (client_ref, status, created_at) idempotent

- 若缺失列则补齐：
  - client_ref TEXT
  - status     TEXT
  - created_at TIMESTAMP DEFAULT NOW()
- 幂等：存在则不重复创建；并对历史 NULL 做兜底更新。

Revision ID: 20251030_orders_add_minimal_columns
Revises: 20251030_order_lines_use_req_qty
Create Date: 2025-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20251030_orders_add_minimal_columns"
down_revision = "20251030_order_lines_use_req_qty"
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

    # 缺啥补啥（幂等）
    if not _has_col(conn, "orders", "client_ref"):
        op.add_column("orders", sa.Column("client_ref", sa.Text(), nullable=True))
    if not _has_col(conn, "orders", "status"):
        op.add_column("orders", sa.Column("status", sa.Text(), nullable=True))
    if not _has_col(conn, "orders", "created_at"):
        op.add_column("orders", sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=True))

    # 抹平历史 NULL，随后可按需收紧为 NOT NULL（此处先不强制，避免破坏既有数据）
    conn.exec_driver_sql("""
        UPDATE orders
        SET client_ref = COALESCE(client_ref, 'N/A'),
            status     = COALESCE(status, 'CREATED'),
            created_at = COALESCE(created_at, NOW())
    """)

def downgrade():
    # 保守回退：仅在列存在时删除
    conn = op.get_bind()

    for col in ("created_at", "status", "client_ref"):
        if _has_col(conn, "orders", col):
            op.drop_column("orders", col)
