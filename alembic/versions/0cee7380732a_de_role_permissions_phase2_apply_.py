"""de_role_permissions_phase2_apply_subpages_seed

Revision ID: 0cee7380732a
Revises: 5f2093e06c0c
Create Date: 2026-04-05 16:20:48.883681

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0cee7380732a'
down_revision: Union[str, Sequence[str], None] = '5f2093e06c0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
