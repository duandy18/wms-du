"""phase3: drop stocks qty_on_hand and sync trigger; slim ledger uq (optional)

Revision ID: 41cb83fb3b2c
Revises: 20251111_sync_qty_columns
Create Date: 2025-11-12 10:23:34.151568

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '41cb83fb3b2c'
down_revision: Union[str, Sequence[str], None] = '20251111_sync_qty_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
