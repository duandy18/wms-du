"""orders fulliment status

Revision ID: 150d827e9834
Revises: 7e2f4ccfef3b
Create Date: 2026-01-17 16:53:03.309272

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "150d827e9834"
down_revision: Union[str, Sequence[str], None] = "7e2f4ccfef3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("orders", sa.Column("service_warehouse_id", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("fulfillment_warehouse_id", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("fulfillment_status", sa.String(length=32), nullable=True))
    op.add_column("orders", sa.Column("blocked_detail", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("blocked_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.add_column("orders", sa.Column("overridden_by", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("override_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("orders", "override_reason")
    op.drop_column("orders", "overridden_at")
    op.drop_column("orders", "overridden_by")

    op.drop_column("orders", "blocked_reasons")
    op.drop_column("orders", "blocked_detail")
    op.drop_column("orders", "fulfillment_status")
    op.drop_column("orders", "fulfillment_warehouse_id")
    op.drop_column("orders", "service_warehouse_id")
