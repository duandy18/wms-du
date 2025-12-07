"""merge heads after snapshots updated_at

Revision ID: 63af7f94ad50
Revises: 20251028_stock_snapshots_add_updated_at, fe9dbc4cf180
Create Date: 2025-10-28 13:44:15.175810

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "63af7f94ad50"
down_revision: Union[str, Sequence[str], None] = (
    "20251028_stock_snapshots_add_updated_at",
    "fe9dbc4cf180",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
