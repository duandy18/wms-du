"""merge heads: pricing template index fix

Revision ID: c09c673dc0de
Revises: 819c6fec1439, 02a284d9351c
Create Date: 2026-03-20 17:51:40.388199

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c09c673dc0de'
down_revision: Union[str, Sequence[str], None] = ('819c6fec1439', '02a284d9351c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
