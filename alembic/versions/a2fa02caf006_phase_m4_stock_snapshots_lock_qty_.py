"""phase m4: stock_snapshots lock qty nonneg and balance

Revision ID: a2fa02caf006
Revises: eb1164b87d2b
Create Date: 2026-03-01 13:18:26.641733

- enforce qty / qty_allocated / qty_available non-negative
- enforce qty_available + qty_allocated = qty
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2fa02caf006"
down_revision: Union[str, Sequence[str], None] = "eb1164b87d2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ------------------------------------------------------------------
    # 1) qty must be >= 0
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_stock_snapshots_qty_nonneg",
        "stock_snapshots",
        sa.text("qty >= 0"),
    )

    # ------------------------------------------------------------------
    # 2) qty_allocated must be >= 0
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_stock_snapshots_qty_allocated_nonneg",
        "stock_snapshots",
        sa.text("qty_allocated >= 0"),
    )

    # ------------------------------------------------------------------
    # 3) qty_available must be >= 0
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_stock_snapshots_qty_available_nonneg",
        "stock_snapshots",
        sa.text("qty_available >= 0"),
    )

    # ------------------------------------------------------------------
    # 4) balance invariant:
    #    qty_available + qty_allocated = qty
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_stock_snapshots_qty_balance",
        "stock_snapshots",
        sa.text("qty_available + qty_allocated = qty"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "ck_stock_snapshots_qty_balance",
        "stock_snapshots",
        type_="check",
    )

    op.drop_constraint(
        "ck_stock_snapshots_qty_available_nonneg",
        "stock_snapshots",
        type_="check",
    )

    op.drop_constraint(
        "ck_stock_snapshots_qty_allocated_nonneg",
        "stock_snapshots",
        type_="check",
    )

    op.drop_constraint(
        "ck_stock_snapshots_qty_nonneg",
        "stock_snapshots",
        type_="check",
    )
