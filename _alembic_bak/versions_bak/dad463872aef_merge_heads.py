"""merge heads

Revision ID: dad463872aef
Revises: be72591863f4, d87c00dfc14c
Create Date: 2025-10-06 09:55:46.333726

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "dad463872aef"
down_revision: str | Sequence[str] | None = ("be72591863f4", "d87c00dfc14c")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
