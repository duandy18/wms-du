"""add purchase_orders table (single-line PO v1)

Revision ID: 7150a6cf6d79
Revises: 56e69081e5df
Create Date: 2025-11-27 17:13:38.799525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7150a6cf6d79'
down_revision: Union[str, Sequence[str], None] = '56e69081e5df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
