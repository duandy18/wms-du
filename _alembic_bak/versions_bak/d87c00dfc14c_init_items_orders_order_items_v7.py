"""init items/orders/order_items v7

Revision ID: d87c00dfc14c
Revises: eacea015793d
Create Date: 2025-10-05 22:19:15.203061

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d87c00dfc14c"
down_revision: str | Sequence[str] | None = "eacea015793d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
