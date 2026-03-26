"""add comments for order_shipment_prepare columns

Revision ID: 83e9e071b65c
Revises: f939f9c31d9b
Create Date: 2026-03-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '83e9e071b65c'
down_revision: Union[str, Sequence[str], None] = 'f939f9c31d9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "order_shipment_prepare",
        "address_parse_hint",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        existing_server_default=sa.text("'warning'::character varying"),
        comment="地址解析辅助提示：normal / warning / failed",
    )

    op.alter_column(
        "order_shipment_prepare",
        "address_verified_status",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        existing_server_default=sa.text("'pending'::character varying"),
        comment="人工核验状态：pending / approved",
    )

    op.alter_column(
        "order_shipment_prepare",
        "verified_by",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment="核验通过操作人 users.id",
    )

    op.alter_column(
        "order_shipment_prepare",
        "verified_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
        comment="核验通过时间",
    )


def downgrade() -> None:
    op.alter_column(
        "order_shipment_prepare",
        "verified_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
        comment=None,
    )

    op.alter_column(
        "order_shipment_prepare",
        "verified_by",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment=None,
    )

    op.alter_column(
        "order_shipment_prepare",
        "address_verified_status",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        existing_server_default=sa.text("'pending'::character varying"),
        comment=None,
    )

    op.alter_column(
        "order_shipment_prepare",
        "address_parse_hint",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        existing_server_default=sa.text("'warning'::character varying"),
        comment=None,
    )
