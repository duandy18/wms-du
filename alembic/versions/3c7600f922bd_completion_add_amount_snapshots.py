"""completion add amount snapshots

Revision ID: 3c7600f922bd
Revises: d5c22ae518ba
Create Date: 2026-04-15 22:14:19.218392

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3c7600f922bd"
down_revision: Union[str, Sequence[str], None] = "d5c22ae518ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "purchase_order_line_completion",
        sa.Column("supply_price_snapshot", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "purchase_order_line_completion",
        sa.Column("discount_amount_snapshot", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "purchase_order_line_completion",
        sa.Column("planned_line_amount", sa.Numeric(14, 2), nullable=True),
    )

    op.execute(
        """
        UPDATE purchase_order_line_completion plc
        SET
          supply_price_snapshot = pol.supply_price,
          discount_amount_snapshot = COALESCE(pol.discount_amount, 0::numeric(14, 2)),
          planned_line_amount = (
            COALESCE(pol.supply_price, 0::numeric(12, 2)) * pol.qty_ordered_base
            - COALESCE(pol.discount_amount, 0::numeric(14, 2))
          )::numeric(14, 2)
        FROM purchase_order_lines pol
        WHERE pol.id = plc.po_line_id
        """
    )

    op.create_check_constraint(
        "ck_polc_discount_amount_snapshot_nonneg",
        "purchase_order_line_completion",
        "discount_amount_snapshot >= 0",
    )

    op.alter_column(
        "purchase_order_line_completion",
        "discount_amount_snapshot",
        existing_type=sa.Numeric(14, 2),
        nullable=False,
    )
    op.alter_column(
        "purchase_order_line_completion",
        "planned_line_amount",
        existing_type=sa.Numeric(14, 2),
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "ck_polc_discount_amount_snapshot_nonneg",
        "purchase_order_line_completion",
        type_="check",
    )
    op.drop_column("purchase_order_line_completion", "planned_line_amount")
    op.drop_column("purchase_order_line_completion", "discount_amount_snapshot")
    op.drop_column("purchase_order_line_completion", "supply_price_snapshot")
