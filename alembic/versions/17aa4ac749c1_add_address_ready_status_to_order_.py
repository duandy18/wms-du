"""add_address_ready_status_to_order_shipment_prepare

Revision ID: 17aa4ac749c1
Revises: 8fce9c4b7a12
Create Date: 2026-03-25 15:47:12.494792
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "17aa4ac749c1"
down_revision: Union[str, Sequence[str], None] = "8fce9c4b7a12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ✅ 1. 加字段（默认 pending）
    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "address_ready_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            comment="地址就绪状态：pending / ready（来自 OMS）",
        ),
    )

    # ✅ 2. 加约束
    op.create_check_constraint(
        "ck_order_shipment_prepare_address_ready_status",
        "order_shipment_prepare",
        "address_ready_status IN ('pending', 'ready')",
    )

    # ✅ 3. 加索引（列表页会用）
    op.create_index(
        "ix_order_shipment_prepare_address_ready_status",
        "order_shipment_prepare",
        ["address_ready_status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_order_shipment_prepare_address_ready_status",
        table_name="order_shipment_prepare",
    )

    op.drop_constraint(
        "ck_order_shipment_prepare_address_ready_status",
        "order_shipment_prepare",
        type_="check",
    )

    op.drop_column("order_shipment_prepare", "address_ready_status")
