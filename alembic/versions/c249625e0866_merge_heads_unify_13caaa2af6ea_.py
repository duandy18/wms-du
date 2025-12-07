"""merge heads: unify 13caaa2af6ea + b17d20cf69a3

Revision ID: c249625e0866
Revises: 13caaa2af6ea, b17d20cf69a3
Create Date: 2025-11-03 10:15:49.644625

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "c249625e0866"
down_revision: Union[str, Sequence[str], None] = ("13caaa2af6ea", "b17d20cf69a3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
