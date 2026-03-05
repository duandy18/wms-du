"""add_platform_order_addresses_fact

Revision ID: 5e961df2e5e5
Revises: bc49a23d6ed0
Create Date: 2026-02-13 16:28:11.544855
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "5e961df2e5e5"
down_revision: Union[str, Sequence[str], None] = "bc49a23d6ed0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "platform_order_addresses",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("ext_order_no", sa.String(length=128), nullable=False),
        sa.Column("province", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("province_code", sa.String(length=32), nullable=True),
        sa.Column("city_code", sa.String(length=32), nullable=True),
        sa.Column(
            "raw",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "scope",
            "platform",
            "store_id",
            "ext_order_no",
            name="uq_po_addr_scope_platform_store_ext",
        ),
    )

    op.create_index(
        "ix_po_addr_scope_platform_store_ext",
        "platform_order_addresses",
        ["scope", "platform", "store_id", "ext_order_no"],
        unique=True,
    )

    op.create_index(
        "ix_po_addr_scope_platform_store",
        "platform_order_addresses",
        ["scope", "platform", "store_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_po_addr_scope_platform_store",
        table_name="platform_order_addresses",
    )

    op.drop_index(
        "ix_po_addr_scope_platform_store_ext",
        table_name="platform_order_addresses",
    )

    op.drop_table("platform_order_addresses")
