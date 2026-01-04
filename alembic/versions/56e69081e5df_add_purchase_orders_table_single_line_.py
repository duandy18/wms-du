"""add purchase_orders table (single-line PO v1)

Revision ID: 56e69081e5df
Revises: dc44008dc8c7
Create Date: 2025-11-27 17:13:03.215356

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '56e69081e5df'
down_revision: Union[str, Sequence[str], None] = 'dc44008dc8c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
