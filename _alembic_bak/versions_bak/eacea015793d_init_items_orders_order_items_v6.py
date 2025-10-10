"""init items/orders/order_items v6

Revision ID: eacea015793d
Revises: 08ca516bcc55
Create Date: 2025-10-05 22:08:32.850115

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "eacea015793d"
down_revision: str | Sequence[str] | None = "08ca516bcc55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
