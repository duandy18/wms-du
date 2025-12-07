"""add item weight_kg

Revision ID: 9f4555426904
Revises: 1ddfc22d47c2
Create Date: 2025-12-04 08:27:27.190516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f4555426904'
down_revision: Union[str, Sequence[str], None] = '1ddfc22d47c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add weight_kg column to items."""
    op.add_column(
        "items",
        sa.Column(
            "weight_kg",
            sa.Numeric(10, 3),
            nullable=True,
            comment="单件净重（kg），用于运费预估（不含包材）",
        ),
    )


def downgrade() -> None:
    """Drop weight_kg column from items."""
    op.drop_column("items", "weight_kg")
