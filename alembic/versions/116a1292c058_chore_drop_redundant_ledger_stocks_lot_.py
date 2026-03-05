"""chore: drop redundant ledger/stocks_lot indexes and add ledger warehouse fk

Revision ID: 116a1292c058
Revises: baef8c90d4ea
Create Date: 2026-03-01 12:05:53.793154

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "116a1292c058"
down_revision: Union[str, Sequence[str], None] = "baef8c90d4ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ------------------------------------------------------------------
    # 1) Drop redundant occurred_at indexes on stock_ledger
    #    Keep: ix_stock_ledger_occurred_at
    # ------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS public.idx_stock_ledger_occurred_at")
    op.execute("DROP INDEX IF EXISTS public.ix_ledger_occurred_at")

    # ------------------------------------------------------------------
    # 2) Drop redundant composite index on stocks_lot
    #    Keep: uq_stocks_lot_item_wh_lot (unique index)
    # ------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS public.ix_stocks_lot_item_wh_lot")

    # ------------------------------------------------------------------
    # 3) Add explicit FK: stock_ledger.warehouse_id -> warehouses.id
    # ------------------------------------------------------------------
    op.create_foreign_key(
        constraint_name="fk_stock_ledger_warehouse",
        source_table="stock_ledger",
        referent_table="warehouses",
        local_cols=["warehouse_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Downgrade schema."""

    # ------------------------------------------------------------------
    # 1) Drop warehouse FK
    # ------------------------------------------------------------------
    op.drop_constraint(
        "fk_stock_ledger_warehouse",
        "stock_ledger",
        type_="foreignkey",
    )

    # ------------------------------------------------------------------
    # 2) Recreate dropped stocks_lot composite index
    # ------------------------------------------------------------------
    op.create_index(
        "ix_stocks_lot_item_wh_lot",
        "stocks_lot",
        ["item_id", "warehouse_id", "lot_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 3) Recreate dropped stock_ledger occurred_at indexes
    # ------------------------------------------------------------------
    op.create_index(
        "idx_stock_ledger_occurred_at",
        "stock_ledger",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_ledger_occurred_at",
        "stock_ledger",
        ["occurred_at"],
        unique=False,
    )
