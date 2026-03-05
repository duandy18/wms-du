"""phase_m3 drop lots.item_has_shelf_life_snapshot

Revision ID: a4bcb4173ca4
Revises: 1c0ba6683ef7
Create Date: 2026-02-28 18:37:31.323973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4bcb4173ca4"
down_revision: Union[str, Sequence[str], None] = "1c0ba6683ef7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("lots", "item_has_shelf_life_snapshot")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("lots", sa.Column("item_has_shelf_life_snapshot", sa.Boolean(), nullable=True))
