"""merge v1.1: batches expiry branches

Revision ID: 29ee69c580ea
Revises: 20251101_batches_expiry_constraints, 20251101_batches_add_expiry_columns_and_constraints
Create Date: 2025-11-01 07:56:00.269288

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "29ee69c580ea"
down_revision: Union[str, Sequence[str], None] = (
    "20251101_batches_expiry_constraints",
    "20251101_batches_add_expiry_columns_and_constraints",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
