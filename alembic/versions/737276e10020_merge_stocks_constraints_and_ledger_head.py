"""merge stocks-constraints and ledger head

Revision ID: 737276e10020
Revises: e4b9177afe8d, 20251006_add_constraints_to_stocks
Create Date: 2025-10-14 08:43:10.362871

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "737276e10020"
down_revision: str | Sequence[str] | None = ("e4b9177afe8d", "20251006_add_constraints_to_stocks")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
