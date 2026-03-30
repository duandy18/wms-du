"""refactor pdd order items fact-only rows

Revision ID: 1393224277ee
Revises: 317baeb05eec
Create Date: 2026-03-30 13:38:36.868321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1393224277ee'
down_revision: Union[str, Sequence[str], None] = '317baeb05eec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
