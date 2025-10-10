"""tighten stocks constraints

Revision ID: 084ef2e5298a
Revises: f995a82ac74e
Create Date: 2025-10-06 15:46:53.732285

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "084ef2e5298a"
down_revision: str | Sequence[str] | None = "f995a82ac74e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
