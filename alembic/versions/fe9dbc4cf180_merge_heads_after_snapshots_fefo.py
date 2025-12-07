"""merge heads after snapshots & fefo

Revision ID: fe9dbc4cf180
Revises: 20251028_fefo_partial_cover_index, 20251028_snapshots_uq_by_wh_loc_item
Create Date: 2025-10-28 11:01:58.407739

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "fe9dbc4cf180"
down_revision: Union[str, Sequence[str], None] = (
    "20251028_fefo_partial_cover_index",
    "20251028_snapshots_uq_by_wh_loc_item",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
