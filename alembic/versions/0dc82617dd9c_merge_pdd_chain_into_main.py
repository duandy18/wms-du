"""merge pdd chain into main

Revision ID: 0dc82617dd9c
Revises: fe8d88377401, 20251026_add_store_entities
Create Date: 2025-10-26 13:29:07.441864

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0dc82617dd9c'
down_revision: Union[str, Sequence[str], None] = ('fe8d88377401', '20251026_add_store_entities')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
