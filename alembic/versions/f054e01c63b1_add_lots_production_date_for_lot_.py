"""add lots production_date for lot identity redesign

Revision ID: f054e01c63b1
Revises: cc39721e46a8
Create Date: 2026-04-11 15:01:13.479087

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f054e01c63b1"
down_revision: Union[str, Sequence[str], None] = "cc39721e46a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "lots",
        sa.Column("production_date", sa.Date(), nullable=True),
    )

    op.create_index(
        "ix_lots_wh_item_production_date",
        "lots",
        ["warehouse_id", "item_id", "production_date"],
        unique=False,
        postgresql_where=sa.text("production_date IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_lots_wh_item_production_date", table_name="lots")
    op.drop_column("lots", "production_date")
