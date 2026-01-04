"""abcd1234_p45_fix_batches_add_whid_if_missing

Revision ID: e93b47e8b6b2
Revises: 9a_add_warehouse_id_to_shipping_records
Create Date: 2025-12-07 16:02:24.613723

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'e93b47e8b6b2'
down_revision: Union[str, Sequence[str], None] = '9a_add_warehouse_id_to_shipping_records'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
