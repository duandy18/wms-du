"""chore(fulfillment): forbid READY_TO_FULFILL in fulfillment_status

Revision ID: 58ab06bc364c
Revises: 2783f7ab0896
Create Date: 2026-02-26 15:20:38.772576

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "58ab06bc364c"
down_revision: Union[str, Sequence[str], None] = "2783f7ab0896"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    路 A 最后一刀：
    - 把历史 READY_TO_FULFILL 迁移为纯 routing 语义
    - 替换 check constraint，禁止 READY_TO_FULFILL 复活
    """

    # 1) 先把存量 READY_TO_FULFILL 清理掉（避免加约束时报错）
    # 规则：
    #   - 若 planned_warehouse_id 非空 且 actual_warehouse_id 为空
    #       => 迁移为 SERVICE_ASSIGNED（纯路由语义）
    #   - 否则 => 置为 NULL（UNASSIGNED）
    op.execute(
        sa.text(
            """
            UPDATE order_fulfillment
               SET fulfillment_status = CASE
                   WHEN planned_warehouse_id IS NOT NULL
                        AND actual_warehouse_id IS NULL
                     THEN 'SERVICE_ASSIGNED'
                   ELSE NULL
               END,
                   updated_at = now()
             WHERE fulfillment_status = 'READY_TO_FULFILL'
            """
        )
    )

    # 2) 替换原有约束（原来已禁止 SHIP_COMMITTED/SHIPPED）
    op.drop_constraint(
        "ck_order_fulfillment_status_no_ship_stage",
        "order_fulfillment",
        type_="check",
    )

    # 3) 新约束：禁止 SHIP_COMMITTED / SHIPPED / READY_TO_FULFILL
    op.create_check_constraint(
        "ck_order_fulfillment_status_no_ship_stage",
        "order_fulfillment",
        "fulfillment_status IS NULL OR "
        "fulfillment_status NOT IN "
        "('SHIP_COMMITTED', 'SHIPPED', 'READY_TO_FULFILL')",
    )


def downgrade() -> None:
    """
    回滚：
    - 恢复旧约束（允许 READY_TO_FULFILL，但仍禁止 SHIP_COMMITTED/SHIPPED）
    """
    op.drop_constraint(
        "ck_order_fulfillment_status_no_ship_stage",
        "order_fulfillment",
        type_="check",
    )

    op.create_check_constraint(
        "ck_order_fulfillment_status_no_ship_stage",
        "order_fulfillment",
        "fulfillment_status IS NULL OR "
        "fulfillment_status NOT IN "
        "('SHIP_COMMITTED', 'SHIPPED')",
    )
