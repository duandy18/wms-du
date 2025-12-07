"""channel_inventory: add visible column (idempotent)

为 channel_inventory 增加 visible INTEGER DEFAULT 0 列，兼容测试用例直接读取：
SELECT COALESCE(visible, 0) ...

Revision ID: 20251030_channel_inventory_add_visible
Revises: 20251030_reservations_add_order_and_batch
Create Date: 2025-10-30
"""

from alembic import op
import sqlalchemy as sa

revision = "20251030_channel_inventory_add_visible"
down_revision = "20251030_reservations_add_order_and_batch"  # ← 按你的当前 head 填写；若不同，请改成 `alembic heads -v` 输出的那个ID
branch_labels = None
depends_on = None


def _has_col(conn, table: str, col: str) -> bool:
    return bool(
        conn.exec_driver_sql(
            """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
    """,
            (table, col),
        ).scalar()
    )


def upgrade():
    conn = op.get_bind()
    if not _has_col(conn, "channel_inventory", "visible"):
        op.add_column(
            "channel_inventory",
            sa.Column("visible", sa.Integer(), nullable=True, server_default=sa.text("0")),
        )
        # 去掉默认值，保持列为可空且初始 0
        op.alter_column("channel_inventory", "visible", server_default=None)


def downgrade():
    conn = op.get_bind()
    if _has_col(conn, "channel_inventory", "visible"):
        op.drop_column("channel_inventory", "visible")
