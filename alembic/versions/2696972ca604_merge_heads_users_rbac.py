"""merge heads: users + rbac

Revision ID: 2696972ca604
Revises: 1157c79168a3, init_rbac_tables
Create Date: 2025-09-30 02:38:41.791065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2696972ca604'
down_revision: Union[str, Sequence[str], None] = ('1157c79168a3', 'init_rbac_tables')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
