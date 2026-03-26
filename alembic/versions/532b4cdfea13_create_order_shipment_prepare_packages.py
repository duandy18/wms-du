"""create_order_shipment_prepare_packages

Revision ID: 532b4cdfea13
Revises: 3560f89f2fdb
Create Date: 2026-03-24 19:24:34.580899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '532b4cdfea13'
down_revision: Union[str, Sequence[str], None] = '3560f89f2fdb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "order_shipment_prepare_packages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("package_no", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(10, 3), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="order_shipment_prepare_packages_pkey"),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_order_shipment_prepare_packages_order",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "order_id",
            "package_no",
            name="uq_order_shipment_prepare_packages_order_package_no",
        ),
        sa.CheckConstraint(
            "package_no >= 1",
            name="ck_order_shipment_prepare_packages_package_no_positive",
        ),
        sa.CheckConstraint(
            "weight_kg IS NULL OR weight_kg > 0",
            name="ck_order_shipment_prepare_packages_weight_positive",
        ),
    )

    op.create_index(
        "ix_order_shipment_prepare_packages_order_id",
        "order_shipment_prepare_packages",
        ["order_id"],
        unique=False,
    )

    op.create_index(
        "ix_order_shipment_prepare_packages_order_package_no",
        "order_shipment_prepare_packages",
        ["order_id", "package_no"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_order_shipment_prepare_packages_order_package_no",
        table_name="order_shipment_prepare_packages",
    )
    op.drop_index(
        "ix_order_shipment_prepare_packages_order_id",
        table_name="order_shipment_prepare_packages",
    )

    op.drop_table("order_shipment_prepare_packages")
