"""Add lock flag to PMS item attribute options.

Revision ID: 20260430111143
Revises: 20260430101727
Create Date: 2026-04-30

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260430111143"
down_revision: Union[str, Sequence[str], None] = "20260430101727"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_attribute_options",
        sa.Column("is_locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("item_attribute_options", "is_locked")
