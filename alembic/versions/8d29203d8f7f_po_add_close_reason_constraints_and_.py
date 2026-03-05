"""po: add close_reason constraints and close invariants

Revision ID: 8d29203d8f7f
Revises: 71f615ca4529
Create Date: 2026-02-19 12:18:42.543836

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d29203d8f7f'
down_revision: Union[str, Sequence[str], None] = '71f615ca4529'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
