"""sqlite: inline INTEGER PRIMARY KEY for core tables

Revision ID: 1088800f816e
Revises: 3a_fix_sqlite_inline_pks
Create Date: 2025-10-06 23:45:53.728638

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "1088800f816e"
down_revision: str | Sequence[str] | None = "3a_fix_sqlite_inline_pks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
