"""create warehouses if missing + ensure MAIN seed

Revision ID: 20251112_create_warehouses_if_missing
Revises: 20251112_seed_main_warehouse
Create Date: 2025-11-12 13:20:00
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "20251112_create_warehouses_if_missing"
down_revision: Union[str, Sequence[str], None] = "20251112_seed_main_warehouse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 若表不存在则创建一个最小可用版本（与现用字段对齐：id, name）
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.warehouses') IS NULL THEN
            CREATE TABLE warehouses (
              id   SERIAL PRIMARY KEY,
              name TEXT   NOT NULL
            );
            -- 也可在这里按需再加列，但我们只创建最小字段集以满足当前代码
          END IF;
        END $$;
        """
    )

    # 2) 保证 name 唯一（用新索引名以避免命名冲突）
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_warehouses_name_uq ON warehouses(name)")

    # 3) 幂等插入 MAIN 仓
    op.execute("INSERT INTO warehouses(name) VALUES ('MAIN') ON CONFLICT (name) DO NOTHING")


def downgrade() -> None:
    # 只删除 MAIN 种子与本迁移创建的索引；不主动删表（避免影响已有数据）
    op.execute("DELETE FROM warehouses WHERE name='MAIN'")
    op.execute("DROP INDEX IF EXISTS ix_warehouses_name_uq")
