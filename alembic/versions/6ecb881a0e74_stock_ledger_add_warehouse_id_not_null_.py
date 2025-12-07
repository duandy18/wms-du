"""stock_ledger: add warehouse_id (NOT NULL) + index

Revision ID: 6ecb881a0e74
Revises: 8fb01b40a389
Create Date: 2025-11-08 09:17:55.500577

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "6ecb881a0e74"
down_revision: Union[str, Sequence[str], None] = "8fb01b40a389"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
