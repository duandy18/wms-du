"""merge explicit and drop legacy columns heads

Revision ID: 3e4f41e0de8d
Revises: 20251104_rewrite_v_putaway_ledger_recent_explicit, 20251104_drop_stocks_legacy_columns
Create Date: 2025-11-04 11:29:50.437742

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "3e4f41e0de8d"
down_revision: Union[str, Sequence[str], None] = (
    "20251104_rewrite_v_putaway_ledger_recent_explicit",
    "20251104_drop_stocks_legacy_columns",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
