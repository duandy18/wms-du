"""refactor pdd orders fact-only header

Revision ID: 317baeb05eec
Revises: 18f7a496ed6d
Create Date: 2026-03-30 13:12:55.690571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "317baeb05eec"
down_revision: Union[str, Sequence[str], None] = "18f7a496ed6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_pdd_orders_shop_id", table_name="pdd_orders")
    op.drop_index("ix_pdd_orders_admission_status", table_name="pdd_orders")
    op.drop_index("ix_pdd_orders_order_create_status", table_name="pdd_orders")

    op.drop_column("pdd_orders", "shop_id")
    op.drop_column("pdd_orders", "address_check_status")
    op.drop_column("pdd_orders", "item_match_status")
    op.drop_column("pdd_orders", "admission_status")
    op.drop_column("pdd_orders", "order_create_status")
    op.drop_column("pdd_orders", "admission_reason")
    op.drop_column("pdd_orders", "last_error_message")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "pdd_orders",
        sa.Column(
            "last_error_message",
            sa.Text(),
            nullable=True,
            comment="最近一次失败信息",
        ),
    )
    op.add_column(
        "pdd_orders",
        sa.Column(
            "admission_reason",
            sa.String(length=255),
            nullable=True,
            comment="准入裁决原因摘要",
        ),
    )
    op.add_column(
        "pdd_orders",
        sa.Column(
            "order_create_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="内部订单创建状态：pending / created / manual_review / failed",
        ),
    )
    op.add_column(
        "pdd_orders",
        sa.Column(
            "admission_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="OMS 准入状态：pending / admitted / manual_review / rejected",
        ),
    )
    op.add_column(
        "pdd_orders",
        sa.Column(
            "item_match_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="商品映射状态：pending / matched / partial / failed",
        ),
    )
    op.add_column(
        "pdd_orders",
        sa.Column(
            "address_check_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="地址业务可用性校验状态：pending / passed / failed",
        ),
    )
    op.add_column(
        "pdd_orders",
        sa.Column(
            "shop_id",
            sa.String(length=64),
            nullable=False,
            server_default="",
            comment="店铺业务 ID（字符串，与 orders.shop_id 语义对齐）",
        ),
    )

    op.create_index("ix_pdd_orders_order_create_status", "pdd_orders", ["order_create_status"])
    op.create_index("ix_pdd_orders_admission_status", "pdd_orders", ["admission_status"])
    op.create_index("ix_pdd_orders_shop_id", "pdd_orders", ["shop_id"])

    op.execute("UPDATE pdd_orders SET shop_id = '' WHERE shop_id IS NULL")

    op.alter_column(
        "pdd_orders",
        "shop_id",
        server_default=None,
        existing_type=sa.String(length=64),
        existing_nullable=False,
    )
    op.alter_column(
        "pdd_orders",
        "address_check_status",
        server_default=None,
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
    op.alter_column(
        "pdd_orders",
        "item_match_status",
        server_default=None,
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
    op.alter_column(
        "pdd_orders",
        "admission_status",
        server_default=None,
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
    op.alter_column(
        "pdd_orders",
        "order_create_status",
        server_default=None,
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
