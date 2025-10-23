"""merge heads (Phase 2.7)

Revision ID: 4075f8906b87
Revises: u8_items_unit_default, 2_7_010_create_platform_shops
Create Date: 2025-10-22 16:22:36.618340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4075f8906b87'
down_revision: Union[str, Sequence[str], None] = ('u8_items_unit_default', '2_7_010_create_platform_shops')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
