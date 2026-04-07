"""grant_admin_business_page_permissions

Revision ID: d97dd0feb8fa
Revises: 528dd15892b9
Create Date: 2026-04-07 02:28:05.046567

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd97dd0feb8fa'
down_revision: Union[str, Sequence[str], None] = '528dd15892b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
