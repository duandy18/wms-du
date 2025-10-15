"""merge 31fc and 3b into single head

Revision ID: 0befa700cb0e
Revises: 31fc28eac057
Create Date: 2025-10-12 17:14:05.708736

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0befa700cb0e"
down_revision: str | Sequence[str] | None = "31fc28eac057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
