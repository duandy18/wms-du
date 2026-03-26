"""add order_shipment_prepare table

Revision ID: f939f9c31d9b
Revises: 79ee0e3665a3
Create Date: 2026-03-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f939f9c31d9b'
down_revision: Union[str, Sequence[str], None] = '79ee0e3665a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_shipment_prepare",
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "address_parse_hint",
            sa.String(length=16),
            nullable=False,
            server_default="warning",
        ),
        sa.Column(
            "address_verified_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "verified_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
        sa.CheckConstraint(
            "address_parse_hint IN ('normal', 'warning', 'failed')",
            name="ck_order_shipment_prepare_parse_hint",
        ),
        sa.CheckConstraint(
            "address_verified_status IN ('pending', 'approved')",
            name="ck_order_shipment_prepare_verified_status",
        ),
    )

    op.create_index(
        "ix_order_shipment_prepare_verified_status",
        "order_shipment_prepare",
        ["address_verified_status"],
        unique=False,
    )

    op.create_index(
        "ix_order_shipment_prepare_parse_hint",
        "order_shipment_prepare",
        ["address_parse_hint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_order_shipment_prepare_parse_hint",
        table_name="order_shipment_prepare",
    )
    op.drop_index(
        "ix_order_shipment_prepare_verified_status",
        table_name="order_shipment_prepare",
    )
    op.drop_table("order_shipment_prepare")
