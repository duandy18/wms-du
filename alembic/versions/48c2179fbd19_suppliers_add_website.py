"""suppliers add website

Revision ID: 48c2179fbd19
Revises: b794e7b1fa73
Create Date: 2025-12-13 13:47:50.166320
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "48c2179fbd19"
down_revision: Union[str, Sequence[str], None] = "b794e7b1fa73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "suppliers",
        sa.Column("website", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("suppliers", "website")
