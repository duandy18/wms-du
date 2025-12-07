"""add warehouse_id to shipping_records

Revision ID: 9a_add_warehouse_id_to_shipping_records
Revises: 8e95974764b1
Create Date: 2025-12-04 12:20:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a_add_warehouse_id_to_shipping_records"
down_revision: Union[str, Sequence[str], None] = "8e95974764b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shipping_records",
        sa.Column("warehouse_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shipping_records", "warehouse_id")
