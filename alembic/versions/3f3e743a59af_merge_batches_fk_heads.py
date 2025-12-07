"""merge: batches FK heads

Revision ID: 3f3e743a59af
Revises: 20251111_add_fk_batches_item, 20251111_add_fk_batches_item_not_valid
Create Date: 2025-11-11 22:08:47.511161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f3e743a59af'
down_revision: Union[str, Sequence[str], None] = ('20251111_add_fk_batches_item', '20251111_add_fk_batches_item_not_valid')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
