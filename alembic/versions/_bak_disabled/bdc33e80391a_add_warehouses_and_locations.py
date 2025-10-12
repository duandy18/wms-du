"""add warehouses and locations

Revision ID: bdc33e80391a
Revises: 1223487447f9
Create Date: 2025-10-12 14:15:10.600896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bdc33e80391a'
down_revision: Union[str, Sequence[str], None] = '1223487447f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
