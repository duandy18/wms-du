"""orders warehouse fk restrict + drop duplicate warehouses name unique

Revision ID: 9f1b212406da
Revises: e9c6712f47a6
Create Date: 2025-12-13 11:32:09.653267

目标（Phase 3 延展一致性）：
1) orders.warehouse_id 外键：ON DELETE SET NULL -> ON DELETE RESTRICT
   - 防止删除仓库导致历史订单丢失仓库坐标
2) warehouses.name 唯一约束去重：
   - 删除重复的 warehouses_name_key（保留 uq_warehouses_name）
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f1b212406da"
down_revision: Union[str, Sequence[str], None] = "e9c6712f47a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 删除重复的 warehouses_name_key（如果存在）
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conname = 'warehouses_name_key'
              ) THEN
                ALTER TABLE warehouses
                  DROP CONSTRAINT warehouses_name_key;
              END IF;
            END $$;
            """
        )
    )

    # 2) orders.warehouse 外键改为 RESTRICT
    op.drop_constraint("fk_orders_warehouse", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_warehouse",
        "orders",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # 回滚：orders 外键恢复为 SET NULL
    op.drop_constraint("fk_orders_warehouse", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_warehouse",
        "orders",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 回滚不恢复 warehouses_name_key（避免把冗余约束引回）
