"""add shipping_providers.warehouse_id

Revision ID: abc28dab3b45
Revises: 3010e1edaadc
Create Date: 2026-01-25 16:14:41.624981
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "abc28dab3b45"
down_revision: Union[str, Sequence[str], None] = "3010e1edaadc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    sql = sa.text(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :t
          AND column_name = :c
        LIMIT 1
        """
    )
    row = bind.execute(sql, {"t": table, "c": column}).fetchone()
    return row is not None


def upgrade() -> None:
    # ✅ 1) add column only if missing
    if not _column_exists("shipping_providers", "warehouse_id"):
        op.add_column("shipping_providers", sa.Column("warehouse_id", sa.Integer(), nullable=True))

        # backfill
        op.execute(
            """
            WITH best_active AS (
              SELECT DISTINCT ON (wsp.shipping_provider_id)
                     wsp.shipping_provider_id AS pid,
                     wsp.warehouse_id AS wid
                FROM warehouse_shipping_providers wsp
               WHERE wsp.active = true
               ORDER BY wsp.shipping_provider_id, wsp.priority ASC, wsp.id ASC
            ),
            best_any AS (
              SELECT DISTINCT ON (wsp.shipping_provider_id)
                     wsp.shipping_provider_id AS pid,
                     wsp.warehouse_id AS wid
                FROM warehouse_shipping_providers wsp
               ORDER BY wsp.shipping_provider_id, wsp.priority ASC, wsp.id ASC
            )
            UPDATE shipping_providers sp
               SET warehouse_id = COALESCE(ba.wid, bn.wid)
              FROM best_active ba
              FULL OUTER JOIN best_any bn ON bn.pid = ba.pid
             WHERE sp.id = COALESCE(ba.pid, bn.pid)
               AND sp.warehouse_id IS NULL;
            """
        )

        op.execute(
            """
            UPDATE shipping_providers
               SET warehouse_id = (SELECT MIN(id) FROM warehouses)
             WHERE warehouse_id IS NULL;
            """
        )

        op.alter_column("shipping_providers", "warehouse_id", nullable=False)

    # ✅ 2) ensure index exists
    # create_index 没有 IF NOT EXISTS，所以用 try/except 防重复
    try:
        op.create_index("ix_shipping_providers_warehouse_id", "shipping_providers", ["warehouse_id"])
    except Exception:
        pass

    # ✅ 3) ensure FK exists
    try:
        op.create_foreign_key(
            "fk_shipping_providers_warehouse_id",
            "shipping_providers",
            "warehouses",
            ["warehouse_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    except Exception:
        pass


def downgrade() -> None:
    # downgrade 做“尽力而为”，避免重复 drop 报错
    try:
        op.drop_constraint("fk_shipping_providers_warehouse_id", "shipping_providers", type_="foreignkey")
    except Exception:
        pass
    try:
        op.drop_index("ix_shipping_providers_warehouse_id", table_name="shipping_providers")
    except Exception:
        pass
    if _column_exists("shipping_providers", "warehouse_id"):
        op.drop_column("shipping_providers", "warehouse_id")
