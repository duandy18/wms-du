"""merge heads: scheme and template lines

Revision ID: 116cb813537d
Revises: 97cad3594e6c, c09c673dc0de
Create Date: 2026-03-20 17:59:22.584479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '116cb813537d'
down_revision: Union[str, Sequence[str], None] = ('97cad3594e6c', 'c09c673dc0de')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
