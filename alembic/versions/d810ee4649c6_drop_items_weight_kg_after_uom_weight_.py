"""drop items weight_kg after uom weight migration

Revision ID: d810ee4649c6
Revises: 6994653cf477
Create Date: 2026-04-10 13:22:55.680687

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d810ee4649c6"
down_revision: Union[str, Sequence[str], None] = "6994653cf477"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("items", "weight_kg")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "items",
        sa.Column(
            "weight_kg",
            sa.Numeric(10, 3),
            nullable=True,
            comment="单件净重（kg），用于运费预估，不含包材",
        ),
    )
