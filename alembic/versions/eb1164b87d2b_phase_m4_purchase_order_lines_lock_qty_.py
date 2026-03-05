"""phase m4: purchase_order_lines lock qty_base contract

Revision ID: eb1164b87d2b
Revises: 9cda2246105e
Create Date: 2026-03-01 13:03:37.454712

- enforce qty_ordered_base = qty_ordered_input * purchase_ratio_to_base_snapshot
- remove default 0 on qty_ordered_base (avoid default violating CHECK)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "eb1164b87d2b"
down_revision: Union[str, Sequence[str], None] = "9cda2246105e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ------------------------------------------------------------------
    # 1) add base contract consistency check
    #    qty_ordered_base must equal qty_ordered_input * purchase_ratio_to_base_snapshot
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_po_lines_qty_base_consistent",
        "purchase_order_lines",
        sa.text(
            "qty_ordered_base = (qty_ordered_input * purchase_ratio_to_base_snapshot)"
        ),
    )

    # ------------------------------------------------------------------
    # 2) drop default 0 on qty_ordered_base
    #    default 0 + CHECK (>0) is a structural footgun
    # ------------------------------------------------------------------
    op.alter_column(
        "purchase_order_lines",
        "qty_ordered_base",
        existing_type=sa.Integer(),
        server_default=None,
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    # restore default 0
    op.alter_column(
        "purchase_order_lines",
        "qty_ordered_base",
        existing_type=sa.Integer(),
        server_default=sa.text("0"),
        existing_nullable=False,
    )

    # drop consistency check
    op.drop_constraint(
        "ck_po_lines_qty_base_consistent",
        "purchase_order_lines",
        type_="check",
    )
