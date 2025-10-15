"""merge 31fc28eac057 and 3b_add_warehouses_locations into single head

Revision ID: 7g_merge_31fc28eac057_3b
Revises: 31fc28eac057, 3b_add_warehouses_locations
Create Date: 2025-10-12 23:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401

from alembic import op  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "7g_merge_31fc28eac057_3b"
down_revision: str | Sequence[str] | None = (
    "31fc28eac057",
    "3b_add_warehouses_locations",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # merge-only migration: no DDL
    pass


def downgrade() -> None:
    # split back into parallel heads: still no DDL
    pass
