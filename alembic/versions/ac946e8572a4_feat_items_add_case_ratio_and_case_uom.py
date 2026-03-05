"""feat(items): add case_ratio and case_uom

Revision ID: ac946e8572a4
Revises: b2aa0c90d971
Create Date: 2026-02-21 11:39:10.592005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ac946e8572a4"
down_revision: Union[str, Sequence[str], None] = "b2aa0c90d971"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("case_ratio", sa.Integer(), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column("case_uom", sa.String(length=16), nullable=True),
    )

    op.create_check_constraint(
        "ck_items_case_ratio_ge_1",
        "items",
        "case_ratio IS NULL OR case_ratio >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_items_case_ratio_ge_1", "items", type_="check")
    op.drop_column("items", "case_uom")
    op.drop_column("items", "case_ratio")
