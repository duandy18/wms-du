"""phase: harden lot-world invariants

Revision ID: 0498ee6abd6d
Revises: 00ab40d84c08
Create Date: 2026-03-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0498ee6abd6d"
down_revision: Union[str, Sequence[str], None] = "00ab40d84c08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Harden Lot-World invariants.

    Adds three critical database-level guards:

    1) lots: enforce consistency between lot_code_source and lot_code
       SUPPLIER → lot_code must NOT be NULL
       INTERNAL → lot_code must be NULL

    2) stocks_lot: forbid negative inventory balance

    3) stock_ledger: forbid negative after_qty
    """

    # ------------------------------------------------------
    # 1. lots source vs lot_code invariant
    # ------------------------------------------------------
    op.create_check_constraint(
        "ck_lots_lot_code_by_source",
        "lots",
        """
        (lot_code_source = 'SUPPLIER' AND lot_code IS NOT NULL)
        OR
        (lot_code_source = 'INTERNAL' AND lot_code IS NULL)
        """,
    )

    # ------------------------------------------------------
    # 2. stocks_lot: balance must be non-negative
    # ------------------------------------------------------
    op.create_check_constraint(
        "ck_stocks_lot_qty_nonneg",
        "stocks_lot",
        "qty >= 0",
    )

    # ------------------------------------------------------
    # 3. stock_ledger: after_qty must be non-negative
    # ------------------------------------------------------
    op.create_check_constraint(
        "ck_stock_ledger_after_qty_nonneg",
        "stock_ledger",
        "after_qty >= 0",
    )


def downgrade() -> None:
    """Rollback hardening constraints."""

    op.drop_constraint(
        "ck_stock_ledger_after_qty_nonneg",
        "stock_ledger",
        type_="check",
    )

    op.drop_constraint(
        "ck_stocks_lot_qty_nonneg",
        "stocks_lot",
        type_="check",
    )

    op.drop_constraint(
        "ck_lots_lot_code_by_source",
        "lots",
        type_="check",
    )
