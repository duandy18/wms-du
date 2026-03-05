"""phase: relax internal lot source receipt constraint

Revision ID: 913f9087f201
Revises: 0498ee6abd6d
Create Date: 2026-03-04

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers
revision: str = "913f9087f201"
down_revision: Union[str, Sequence[str], None] = "0498ee6abd6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Replace legacy INTERNAL lot constraint.

    Old rule:
        INTERNAL lots must always bind source_receipt_id/source_line_no.

    New rule:
        source_receipt_id/source_line_no must appear as a pair
        (both NULL or both NOT NULL).
    """

    # drop legacy constraint
    op.drop_constraint(
        "ck_lots_internal_requires_source_receipt_line",
        "lots",
        type_="check",
    )

    # create new pair constraint
    op.create_check_constraint(
        "ck_lots_internal_source_receipt_line_pair",
        "lots",
        """
        (lot_code_source <> 'INTERNAL')
        OR (
            (source_receipt_id IS NULL AND source_line_no IS NULL)
            OR
            (source_receipt_id IS NOT NULL AND source_line_no IS NOT NULL)
        )
        """,
    )


def downgrade() -> None:
    """Rollback constraint change."""

    op.drop_constraint(
        "ck_lots_internal_source_receipt_line_pair",
        "lots",
        type_="check",
    )

    op.create_check_constraint(
        "ck_lots_internal_requires_source_receipt_line",
        "lots",
        """
        (lot_code_source <> 'INTERNAL')
        OR (source_receipt_id IS NOT NULL AND source_line_no IS NOT NULL)
        """,
    )
