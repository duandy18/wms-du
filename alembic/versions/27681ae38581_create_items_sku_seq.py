"""create items_sku_seq

Revision ID: 27681ae38581
Revises: 8a6e7c773be0
Create Date: 2026-02-06 12:01:54.761015

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "27681ae38581"
down_revision: Union[str, Sequence[str], None] = "8a6e7c773be0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS items_sku_seq")


def downgrade() -> None:
    # 保守回滚：不删 sequence
    return
