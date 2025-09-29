"""merge heads

Revision ID: 9ffd3baeaf74
Revises: 1157c79168a3, 747ee02c3630
Create Date: 2025-09-29 20:43:23.008550

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ffd3baeaf74"
down_revision: Union[str, Sequence[str], None] = ("1157c79168a3", "747ee02c3630")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
