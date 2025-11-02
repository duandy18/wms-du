"""order_lines: standardize quantity column to req_qty (idempotent)

- 若存在 req_qty：保持不变
- 若不存在 req_qty 但存在 qty：重命名 qty -> req_qty
- 若两者都不存在：新增 req_qty INT NOT NULL（短暂 DEFAULT 0 以通过约束，随后移除默认）
- 若 orders / order_lines 不存在：创建最小表结构（含 req_qty）

Revision ID: 20251030_order_lines_use_req_qty
Revises: 20251030_set_batches_qty_default_zero
Create Date: 2025-10-30
"""

from alembic import op
import sqlalchemy as sa


# --- 元信息 ---
revision = "20251030_order_lines_use_req_qty"
down_revision = "20251030_set_batches_qty_default_zero"
branch_labels = None
depends_on = None


# --- 工具函数 ---
def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.exec_driver_sql(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema='public' AND table_name=%s
            LIMIT 1
            """,
            (table,),
        ).scalar()
    )


def _has_col(conn, table: str, col: str) -> bool:
    return bool(
        conn.exec_driver_sql(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s AND column_name=%s
            LIMIT 1
            """,
            (table, col),
        ).scalar()
    )


# --- 迁移实现 ---
def upgrade() -> None:
    conn = op.get_bind()

    # 0) 若 orders 不存在，先创建最小表
    if not _table_exists(conn, "orders"):
        op.create_table(
            "orders",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("client_ref", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
        )

    # 1) 若 order_lines 不存在，直接创建“标准版”（含 req_qty）
    if not _table_exists(conn, "order_lines"):
        op.create_table(
            "order_lines",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "order_id",
                sa.BigInteger(),
                sa.ForeignKey("orders.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("item_id", sa.BigInteger(), nullable=False),
            sa.Column("req_qty", sa.Integer(), nullable=False),
        )
        op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"], unique=False)
        return  # 新表已到位，后续无须再处理列名统一

    # 2) 已有 order_lines 表：统一列名为 req_qty
    has_req = _has_col(conn, "order_lines", "req_qty")
    has_qty = _has_col(conn, "order_lines", "qty")

    if not has_req and has_qty:
        # 仅有 qty：重命名为 req_qty
        op.alter_column(
            "order_lines",
            "qty",
            new_column_name="req_qty",
            existing_type=sa.Integer(),
        )
    elif not has_req and not has_qty:
        # 两者都没有：新增 req_qty（短暂 DEFAULT 0 以通过 NOT NULL）
        op.add_column(
            "order_lines",
            sa.Column("req_qty", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
        # 移除默认值，保持纯约束
        op.alter_column("order_lines", "req_qty", server_default=None)


def downgrade() -> None:
    # 保守回退：若有 req_qty 且没有 qty，则把 req_qty 改回 qty
    conn = op.get_bind()

    def _has(table: str, col: str) -> bool:
        return bool(
            conn.exec_driver_sql(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s AND column_name=%s
                LIMIT 1
                """,
                (table, col),
            ).scalar()
        )

    if _has("order_lines", "req_qty") and not _has("order_lines", "qty"):
        op.alter_column(
            "order_lines",
            "req_qty",
            new_column_name="qty",
            existing_type=sa.Integer(),
        )
