"""add platform shop to orders

Revision ID: 4b02a324aca4
Revises: 41cb83fb3b2c
Create Date: 2025-11-12 11:19:37.379223
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "4b02a324aca4"
down_revision: Union[str, Sequence[str], None] = "41cb83fb3b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------- small helpers (server-side checks) ----------
def _col_exists(conn, table: str, col: str) -> bool:
    res = conn.exec_driver_sql(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
        """,
        (table, col),
    ).first()
    return res is not None


def _constraint_exists(conn, name: str) -> bool:
    res = conn.exec_driver_sql(
        "SELECT 1 FROM pg_constraint WHERE conname=%s LIMIT 1", (name,)
    ).first()
    return res is not None


def _index_exists(conn, name: str) -> bool:
    res = conn.exec_driver_sql(
        """
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind='i' AND c.relname=%s AND n.nspname='public'
        LIMIT 1
        """,
        (name,),
    ).first()
    return res is not None


# --------------------------- upgrade ---------------------------
def upgrade() -> None:
    conn = op.get_bind()

    # 1) add columns if missing (NULLable with defaults first)
    if not _col_exists(conn, "orders", "platform"):
        op.add_column(
            "orders",
            sa.Column("platform", sa.String(32), nullable=True, server_default=sa.text("'UNKNOWN'")),
        )
    if not _col_exists(conn, "orders", "shop_id"):
        op.add_column(
            "orders",
            sa.Column("shop_id", sa.String(128), nullable=True, server_default=sa.text("'UNKNOWN'")),
        )
    if not _col_exists(conn, "orders", "ext_order_no"):
        op.add_column(
            "orders",
            sa.Column("ext_order_no", sa.String(128), nullable=True, server_default=sa.text("''")),
        )

    # 2) backfill & set NOT NULL, then drop defaults
    # (safe even if column just created; if existed before, ensures compatibility)
    op.execute("UPDATE orders SET platform='UNKNOWN' WHERE platform IS NULL")
    op.execute("UPDATE orders SET shop_id='UNKNOWN' WHERE shop_id IS NULL")
    op.execute("UPDATE orders SET ext_order_no='' WHERE ext_order_no IS NULL")

    op.alter_column("orders", "platform", existing_type=sa.String(32), nullable=False)
    op.alter_column("orders", "shop_id", existing_type=sa.String(128), nullable=False)
    op.alter_column("orders", "ext_order_no", existing_type=sa.String(128), nullable=False)

    op.alter_column("orders", "platform", server_default=None)
    op.alter_column("orders", "shop_id", server_default=None)
    op.alter_column("orders", "ext_order_no", server_default=None)

    # 3) unique constraint (idempotent)
    if not _constraint_exists(conn, "uq_orders_platform_shop_ext"):
        op.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname='uq_orders_platform_shop_ext'
              ) THEN
                ALTER TABLE orders
                ADD CONSTRAINT uq_orders_platform_shop_ext
                UNIQUE (platform, shop_id, ext_order_no);
              END IF;
            END $$;
            """
        )

    # 4) helper index (optional; idempotent)
    if not _index_exists(conn, "ix_orders_platform_shop"):
        op.execute("CREATE INDEX ix_orders_platform_shop ON orders (platform, shop_id)")


# -------------------------- downgrade --------------------------
def downgrade() -> None:
    conn = op.get_bind()

    # drop unique constraint if exists
    if _constraint_exists(conn, "uq_orders_platform_shop_ext"):
        op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS uq_orders_platform_shop_ext")

    # drop index if exists
    if _index_exists(conn, "ix_orders_platform_shop"):
        op.execute("DROP INDEX IF EXISTS ix_orders_platform_shop")

    # drop columns if they exist (reverse order is fine)
    if _col_exists(conn, "orders", "ext_order_no"):
        op.drop_column("orders", "ext_order_no")
    if _col_exists(conn, "orders", "shop_id"):
        op.drop_column("orders", "shop_id")
    if _col_exists(conn, "orders", "platform"):
        op.drop_column("orders", "platform")
