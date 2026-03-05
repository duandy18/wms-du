"""drop inventory_movements legacy table

Revision ID: 9b2e6b38fc8b
Revises: a1108cfc2d66
Create Date: 2026-03-05 18:02:32.237508
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b2e6b38fc8b"
down_revision: Union[str, Sequence[str], None] = "a1108cfc2d66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # legacy table not used in lot-world architecture
    op.execute("DROP TABLE IF EXISTS inventory_movements;")


def downgrade() -> None:
    # legacy table intentionally not restored
    pass
