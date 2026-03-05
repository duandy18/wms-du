"""feat(outbound): replace fulfillment status ship machine with ship_committed_at/shipped_at

Revision ID: 2783f7ab0896
Revises: ba7bdfb8e243
Create Date: 2026-02-26 14:51:57.324597

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2783f7ab0896"
down_revision: Union[str, Sequence[str], None] = "ba7bdfb8e243"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 新增事实字段（替代 fulfillment_status 的 SHIP 子状态机）
    op.add_column(
        "order_fulfillment",
        sa.Column("ship_committed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "order_fulfillment",
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2) 数据迁移：把旧 fulfillment_status 的阶段语义搬到事实字段，再清空 status
    # - SHIP_COMMITTED: ship_committed_at = COALESCE(ship_committed_at, updated_at)
    # - SHIPPED:        shipped_at = COALESCE(shipped_at, updated_at)
    #                  ship_committed_at = COALESCE(ship_committed_at, shipped_at, updated_at)
    op.execute(
        sa.text(
            """
            UPDATE order_fulfillment
               SET ship_committed_at = COALESCE(ship_committed_at, updated_at),
                   fulfillment_status = NULL,
                   updated_at = now()
             WHERE fulfillment_status = 'SHIP_COMMITTED'
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE order_fulfillment
               SET shipped_at = COALESCE(shipped_at, updated_at),
                   ship_committed_at = COALESCE(ship_committed_at, shipped_at, updated_at),
                   fulfillment_status = NULL,
                   updated_at = now()
             WHERE fulfillment_status = 'SHIPPED'
            """
        )
    )

    # 3) 硬约束：禁止再写入旧阶段值（防止复活）
    op.create_check_constraint(
        "ck_order_fulfillment_status_no_ship_stage",
        "order_fulfillment",
        "fulfillment_status IS NULL OR fulfillment_status NOT IN ('SHIP_COMMITTED', 'SHIPPED')",
    )

    # 4) 事实字段一致性：shipped_at 存在则必须已 committed
    op.create_check_constraint(
        "ck_order_fulfillment_ship_time_order",
        "order_fulfillment",
        "shipped_at IS NULL OR ship_committed_at IS NOT NULL",
    )


def downgrade() -> None:
    # downgrade：先删约束，再尽量把事实字段回填到旧 status（避免信息丢失）
    op.drop_constraint("ck_order_fulfillment_ship_time_order", "order_fulfillment", type_="check")
    op.drop_constraint("ck_order_fulfillment_status_no_ship_stage", "order_fulfillment", type_="check")

    op.execute(
        sa.text(
            """
            UPDATE order_fulfillment
               SET fulfillment_status = 'SHIPPED',
                   updated_at = now()
             WHERE shipped_at IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE order_fulfillment
               SET fulfillment_status = 'SHIP_COMMITTED',
                   updated_at = now()
             WHERE shipped_at IS NULL
               AND ship_committed_at IS NOT NULL
            """
        )
    )

    op.drop_column("order_fulfillment", "shipped_at")
    op.drop_column("order_fulfillment", "ship_committed_at")
