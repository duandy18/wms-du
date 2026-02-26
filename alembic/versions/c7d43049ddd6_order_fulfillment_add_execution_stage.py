"""order_fulfillment_add_execution_stage

Revision ID: c7d43049ddd6
Revises: 3311386fa223
Create Date: 2026-02-26 11:13:40.292090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7d43049ddd6"
down_revision: Union[str, Sequence[str], None] = "3311386fa223"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase 5：为 order_fulfillment 引入显式执行阶段字段 execution_stage。

    目标：
    - execution_stage 成为唯一“执行阶段真相”（RESERVE / PICK / SHIP）
    - fulfillment_status 保留历史/路由/子状态机语义
    """

    # 1️⃣ 新增 execution_stage（先允许 NULL，便于平滑迁移）
    op.add_column(
        "order_fulfillment",
        sa.Column("execution_stage", sa.String(length=16), nullable=True),
    )

    # 2️⃣ 加 CHECK 约束（允许 NULL）
    op.create_check_constraint(
        "ck_order_fulfillment_execution_stage",
        "order_fulfillment",
        "execution_stage IS NULL OR execution_stage IN ('RESERVE','PICK','SHIP')",
    )

    # 3️⃣ 回填：已有 SHIP 子状态机的记录统一提升为 execution_stage='SHIP'
    op.execute(
        """
        UPDATE order_fulfillment
           SET execution_stage = 'SHIP'
         WHERE execution_stage IS NULL
           AND fulfillment_status IN ('SHIP_COMMITTED','SHIPPED')
        """
    )

    # 4️⃣ 建索引（便于运维排查 / 状态统计）
    op.create_index(
        "ix_order_fulfillment_execution_stage",
        "order_fulfillment",
        ["execution_stage"],
        unique=False,
    )


def downgrade() -> None:
    """
    回滚：
    - 删除 execution_stage 列及相关约束/索引
    """

    op.drop_index("ix_order_fulfillment_execution_stage", table_name="order_fulfillment")
    op.drop_constraint(
        "ck_order_fulfillment_execution_stage",
        "order_fulfillment",
        type_="check",
    )
    op.drop_column("order_fulfillment", "execution_stage")
