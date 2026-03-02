"""chore cleanup inbound_receipt_lines duplicate constraints

Revision ID: 0a416b5c1b27
Revises: 3294e8be11b1
Create Date: 2026-02-28 15:38:18.283599

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0a416b5c1b27"
down_revision: Union[str, Sequence[str], None] = "3294e8be11b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Cleanup inbound_receipt_lines:

    - Drop redundant single-column FK:
        fk_inbound_receipt_lines_lot_id
      (Keep composite FK fk_inbound_receipt_lines_lot_dims)

    - Drop duplicate UNIQUE constraint on (receipt_id, line_no):
        uq_inbound_receipt_lines_receipt_line_no
      (Keep uq_inbound_receipt_lines_receipt_line)
    """

    # 1) Drop redundant single-column FK (lot_id -> lots.id)
    op.drop_constraint(
        "fk_inbound_receipt_lines_lot_id",
        "inbound_receipt_lines",
        type_="foreignkey",
    )

    # 2) Drop duplicate UNIQUE constraint
    op.drop_constraint(
        "uq_inbound_receipt_lines_receipt_line_no",
        "inbound_receipt_lines",
        type_="unique",
    )


def downgrade() -> None:
    """
    Downgrade:

    - Restore duplicate UNIQUE (receipt_id, line_no)
    - Restore single-column FK (lot_id) -> lots(id)

    NOTE:
    Downgrade reintroduces redundancy by design (symmetry only).
    """

    # 1) Restore duplicate UNIQUE
    op.create_unique_constraint(
        "uq_inbound_receipt_lines_receipt_line_no",
        "inbound_receipt_lines",
        ["receipt_id", "line_no"],
    )

    # 2) Restore single-column FK
    op.create_foreign_key(
        "fk_inbound_receipt_lines_lot_id",
        "inbound_receipt_lines",
        "lots",
        ["lot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
