"""phase_3_7_create_order_address

Revision ID: ea1ea0953f72
Revises: a3786a01e11a
Create Date: 2025-11-16 11:14:37.456939
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ea1ea0953f72"
down_revision: Union[str, Sequence[str], None] = "a3786a01e11a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create order_address table."""
    op.create_table(
        "order_address",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("receiver_name", sa.String(length=255), nullable=True),
        sa.Column("receiver_phone", sa.String(length=64), nullable=True),
        sa.Column("province", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("district", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.String(length=255), nullable=True),
        sa.Column("zipcode", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_order_address_order",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("order_id", name="uq_order_address_order_id"),
    )
    op.create_index(
        "ix_order_address_order_id",
        "order_address",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop order_address table."""
    op.drop_index("ix_order_address_order_id", table_name="order_address")
    op.drop_table("order_address")
