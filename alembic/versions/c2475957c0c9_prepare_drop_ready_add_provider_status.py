"""prepare_drop_ready_add_provider_status

Revision ID: c2475957c0c9
Revises: 17aa4ac749c1
Create Date: 2026-03-25 17:33:17.877794

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2475957c0c9"
down_revision: Union[str, Sequence[str], None] = "17aa4ac749c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 新增 provider_status
    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "provider_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            comment="快递公司选择状态：pending / selected",
        ),
    )

    # 2) 回填 provider_status
    # 规则：
    # - 若该订单存在至少一个 package
    # - 且该订单下不存在 selected_provider_id 为空的 package
    #   => provider_status = 'selected'
    # - 其他情况 => 'pending'
    op.execute(
        """
        UPDATE order_shipment_prepare p
        SET provider_status = CASE
            WHEN EXISTS (
                SELECT 1
                  FROM order_shipment_prepare_packages pkg
                 WHERE pkg.order_id = p.order_id
            )
            AND NOT EXISTS (
                SELECT 1
                  FROM order_shipment_prepare_packages pkg
                 WHERE pkg.order_id = p.order_id
                   AND pkg.selected_provider_id IS NULL
            )
            THEN 'selected'
            ELSE 'pending'
        END
        """
    )

    # 3) 新增 provider_status 索引
    op.create_index(
        "ix_order_shipment_prepare_provider_status",
        "order_shipment_prepare",
        ["provider_status"],
        unique=False,
    )

    # 4) 新增 provider_status check constraint
    op.create_check_constraint(
        "ck_order_shipment_prepare_provider_status",
        "order_shipment_prepare",
        "provider_status IN ('pending', 'selected')",
    )

    # 5) 删除旧 ready_* 约束 / 索引 / 外键
    op.drop_constraint(
        "ck_order_shipment_prepare_ready_status",
        "order_shipment_prepare",
        type_="check",
    )
    op.drop_index(
        "ix_order_shipment_prepare_ready_status",
        table_name="order_shipment_prepare",
    )
    op.drop_constraint(
        "order_shipment_prepare_ready_by_fkey",
        "order_shipment_prepare",
        type_="foreignkey",
    )

    # 6) 删除旧 ready_* 列
    op.drop_column("order_shipment_prepare", "ready_at")
    op.drop_column("order_shipment_prepare", "ready_by")
    op.drop_column("order_shipment_prepare", "ready_status")


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 恢复 ready_status
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

    # 2) 恢复 ready_by
    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "ready_by",
            sa.Integer(),
            nullable=True,
            comment="标记准备完成操作人 users.id",
        ),
    )

    # 3) 恢复 ready_at
    op.add_column(
        "order_shipment_prepare",
        sa.Column(
            "ready_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="标记准备完成时间",
        ),
    )

    # 4) 恢复 ready_* 外键 / 索引 / check
    op.create_foreign_key(
        "order_shipment_prepare_ready_by_fkey",
        "order_shipment_prepare",
        "users",
        ["ready_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_order_shipment_prepare_ready_status",
        "order_shipment_prepare",
        ["ready_status"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_order_shipment_prepare_ready_status",
        "order_shipment_prepare",
        "ready_status IN ('pending', 'ready')",
    )

    # 5) 删除 provider_status 的 check / 索引 / 列
    op.drop_constraint(
        "ck_order_shipment_prepare_provider_status",
        "order_shipment_prepare",
        type_="check",
    )
    op.drop_index(
        "ix_order_shipment_prepare_provider_status",
        table_name="order_shipment_prepare",
    )
    op.drop_column("order_shipment_prepare", "provider_status")
