"""add uq order_items(order_id, sku_id)

Revision ID: ca7532173d7f
Revises: 4b02a324aca4
Create Date: 2025-11-12 11:24:15.822510
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "ca7532173d7f"
down_revision: Union[str, Sequence[str], None] = "4b02a324aca4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------- helpers ----------------
def _col_exists(conn, table: str, col: str) -> bool:
    r = conn.exec_driver_sql(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        LIMIT 1
        """,
        (table, col),
    ).first()
    return r is not None


def _constraint_exists(conn, name: str) -> bool:
    r = conn.exec_driver_sql(
        "SELECT 1 FROM pg_constraint WHERE conname=%s LIMIT 1", (name,)
    ).first()
    return r is not None


def _index_exists(conn, name: str) -> bool:
    r = conn.exec_driver_sql(
        """
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind='i' AND c.relname=%s AND n.nspname='public'
        LIMIT 1
        """,
        (name,),
    ).first()
    return r is not None


# ---------------- upgrade ----------------
def upgrade() -> None:
    conn = op.get_bind()

    # 1) 前置：必要列是否存在
    need_cols = all(
        _col_exists(conn, "order_items", c) for c in ("order_id", "sku_id")
    )
    if need_cols and not _constraint_exists(conn, "uq_order_items_ord_sku"):
        # 条件式创建唯一约束 (order_id, sku_id)
        op.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname='uq_order_items_ord_sku'
              ) THEN
                ALTER TABLE order_items
                ADD CONSTRAINT uq_order_items_ord_sku
                UNIQUE (order_id, sku_id);
              END IF;
            END $$;
            """
        )

    # 2) 辅助索引（可选，幂等）
    if not _index_exists(conn, "ix_order_items_order"):
        op.execute("CREATE INDEX ix_order_items_order ON order_items (order_id)")
    if not _index_exists(conn, "ix_order_items_item"):
        op.execute("CREATE INDEX ix_order_items_item ON order_items (item_id)")


# ---------------- downgrade ----------------
def downgrade() -> None:
    conn = op.get_bind()

    if _constraint_exists(conn, "uq_order_items_ord_sku"):
        op.execute(
            "ALTER TABLE order_items DROP CONSTRAINT IF EXISTS uq_order_items_ord_sku"
        )

    if _index_exists(conn, "ix_order_items_order"):
        op.execute("DROP INDEX IF EXISTS ix_order_items_order")
    if _index_exists(conn, "ix_order_items_item"):
        op.execute("DROP INDEX IF EXISTS ix_order_items_item")
