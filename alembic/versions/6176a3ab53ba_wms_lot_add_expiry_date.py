"""wms_lot_add_expiry_date

Revision ID: 6176a3ab53ba
Revises: 0e7c789ec00b
Create Date: 2026-04-11 19:48:05.177282

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6176a3ab53ba"
down_revision: Union[str, Sequence[str], None] = "0e7c789ec00b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "lots",
        sa.Column("expiry_date", sa.Date(), nullable=True),
    )

    op.create_check_constraint(
        "ck_lots_production_le_expiry",
        "lots",
        sa.text(
            "(production_date IS NULL) OR "
            "(expiry_date IS NULL) OR "
            "(production_date <= expiry_date)"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "ck_lots_production_le_expiry",
        "lots",
        type_="check",
    )

    op.drop_column("lots", "expiry_date")
