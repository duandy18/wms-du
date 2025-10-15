"""merge heads after baseline

Revision ID: 31fc28eac057
Revises: 084ef2e5298a, 20251006_add_constraints_to_stocks
Create Date: 2025-10-06 15:57:39.545044

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "31fc28eac057"
down_revision: str | Sequence[str] | None = ("084ef2e5298a", "20251006_add_constraints_to_stocks")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
