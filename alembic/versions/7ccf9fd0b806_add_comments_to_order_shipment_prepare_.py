"""add_comments_to_order_shipment_prepare_packages

Revision ID: 7ccf9fd0b806
Revises: 532b4cdfea13
Create Date: 2026-03-24 19:27:59.886882

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ccf9fd0b806'
down_revision: Union[str, Sequence[str], None] = '532b4cdfea13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.alter_column(
        "order_shipment_prepare_packages",
        "order_id",
        existing_type=sa.BigInteger(),
        nullable=False,
        comment="订单 ID",
    )

    op.alter_column(
        "order_shipment_prepare_packages",
        "package_no",
        existing_type=sa.Integer(),
        nullable=False,
        comment="包裹序号，从 1 开始",
    )

    op.alter_column(
        "order_shipment_prepare_packages",
        "weight_kg",
        existing_type=sa.Numeric(10, 3),
        nullable=True,
        comment="包裹重量（kg）",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.alter_column(
        "order_shipment_prepare_packages",
        "weight_kg",
        existing_type=sa.Numeric(10, 3),
        nullable=True,
        comment=None,
    )

    op.alter_column(
        "order_shipment_prepare_packages",
        "package_no",
        existing_type=sa.Integer(),
        nullable=False,
        comment=None,
    )

    op.alter_column(
        "order_shipment_prepare_packages",
        "order_id",
        existing_type=sa.BigInteger(),
        nullable=False,
        comment=None,
    )
