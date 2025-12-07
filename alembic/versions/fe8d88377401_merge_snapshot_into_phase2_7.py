"""merge snapshot into phase2.7

Revision ID: fe8d88377401
Revises: 4075f8906b87, u9_order_state_snapshot
Create Date: 2025-10-23 15:32:44.971011

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "fe8d88377401"
down_revision: Union[str, Sequence[str], None] = ("4075f8906b87", "u9_order_state_snapshot")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
