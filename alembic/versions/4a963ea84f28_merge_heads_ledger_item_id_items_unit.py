"""merge heads: ledger item_id + items.unit

Revision ID: 4a963ea84f28
Revises: 20251015_add_item_id_to_stock_ledger, 20251015_fix_items_unit_column
Create Date: 2025-10-15 17:53:15.709529

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a963ea84f28'
down_revision: Union[str, Sequence[str], None] = ('20251015_add_item_id_to_stock_ledger', '20251015_fix_items_unit_column')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
