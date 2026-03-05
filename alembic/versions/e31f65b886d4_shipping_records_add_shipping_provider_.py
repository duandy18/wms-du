"""shipping_records: add shipping_provider_id

Revision ID: e31f65b886d4
Revises: 63b09d1eb510
Create Date: 2026-03-03 19:06:04.517400

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e31f65b886d4'
down_revision: Union[str, Sequence[str], None] = '63b09d1eb510'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
