"""expand_order_shipment_prepare_for_dispatch_decision

Revision ID: 3560f89f2fdb
Revises: 83e9e071b65c
Create Date: 2026-03-24 18:59:23.783527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3560f89f2fdb'
down_revision: Union[str, Sequence[str], None] = '83e9e071b65c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ===== 新增列 =====
    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "package_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            comment="包裹方案状态：pending / planned",
        ),
    )

    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "pricing_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            comment="运价计算状态：pending / calculated",
        ),
    )

    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "selected_provider_id",
            sa.Integer(),
            nullable=True,
            comment="已选承运商 shipping_providers.id",
        ),
    )

    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "selected_quote_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="已锁定报价快照",
        ),
    )

    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "ready_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            comment="准备完成状态：pending / ready",
        ),
    )

    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "ready_by",
            sa.Integer(),
            nullable=True,
            comment="标记准备完成操作人 users.id",
        ),
    )

    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "ready_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="标记准备完成时间",
        ),
    )

    # ===== 外键 =====
    op.create_foreign_key(
        "order_shipment_prepare_selected_provider_id_fkey",
        "order_shipment_prepare",
        "shipping_providers",
        ["selected_provider_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_foreign_key(
        "order_shipment_prepare_ready_by_fkey",
        "order_shipment_prepare",
        "users",
        ["ready_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # ===== CHECK 约束 =====
    op.create_check_constraint(
        "ck_order_shipment_prepare_package_status",
        "order_shipment_prepare",
        "package_status IN ('pending', 'planned')",
    )

    op.create_check_constraint(
        "ck_order_shipment_prepare_pricing_status",
        "order_shipment_prepare",
        "pricing_status IN ('pending', 'calculated')",
    )

    op.create_check_constraint(
        "ck_order_shipment_prepare_ready_status",
        "order_shipment_prepare",
        "ready_status IN ('pending', 'ready')",
    )

    # ===== 索引 =====
    op.create_index(
        "ix_order_shipment_prepare_package_status",
        "order_shipment_prepare",
        ["package_status"],
        unique=False,
    )

    op.create_index(
        "ix_order_shipment_prepare_pricing_status",
        "order_shipment_prepare",
        ["pricing_status"],
        unique=False,
    )

    op.create_index(
        "ix_order_shipment_prepare_selected_provider_id",
        "order_shipment_prepare",
        ["selected_provider_id"],
        unique=False,
    )

    op.create_index(
        "ix_order_shipment_prepare_ready_status",
        "order_shipment_prepare",
        ["ready_status"],
        unique=False,
    )

    # ===== 移除默认值（只用于数据填充阶段）=====
    op.alter_column("order_shipment_prepare", "package_status", server_default=None)
    op.alter_column("order_shipment_prepare", "pricing_status", server_default=None)
    op.alter_column("order_shipment_prepare", "ready_status", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("ix_order_shipment_prepare_ready_status", table_name="order_shipment_prepare")
    op.drop_index("ix_order_shipment_prepare_selected_provider_id", table_name="order_shipment_prepare")
    op.drop_index("ix_order_shipment_prepare_pricing_status", table_name="order_shipment_prepare")
    op.drop_index("ix_order_shipment_prepare_package_status", table_name="order_shipment_prepare")

    op.drop_constraint(
        "ck_order_shipment_prepare_ready_status",
        "order_shipment_prepare",
        type_="check",
    )
    op.drop_constraint(
        "ck_order_shipment_prepare_pricing_status",
        "order_shipment_prepare",
        type_="check",
    )
    op.drop_constraint(
        "ck_order_shipment_prepare_package_status",
        "order_shipment_prepare",
        type_="check",
    )

    op.drop_constraint(
        "order_shipment_prepare_ready_by_fkey",
        "order_shipment_prepare",
        type_="foreignkey",
    )
    op.drop_constraint(
        "order_shipment_prepare_selected_provider_id_fkey",
        "order_shipment_prepare",
        type_="foreignkey",
    )

    op.drop_column("order_shipment_prepare", "ready_at")
    op.drop_column("order_shipment_prepare", "ready_by")
    op.drop_column("order_shipment_prepare", "ready_status")
    op.drop_column("order_shipment_prepare", "selected_quote_snapshot")
    op.drop_column("order_shipment_prepare", "selected_provider_id")
    op.drop_column("order_shipment_prepare", "pricing_status")
    op.drop_column("order_shipment_prepare", "package_status")
