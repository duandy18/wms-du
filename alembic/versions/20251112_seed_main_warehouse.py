"""seed MAIN warehouse if missing

Revision ID: 20251112_seed_main_warehouse
Revises: ca7532173d7f
Create Date: 2025-11-12 13:05:00
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "20251112_seed_main_warehouse"
down_revision: Union[str, Sequence[str], None] = "ca7532173d7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 用“新名字”的唯一索引，规避既有同名 relation 冲突
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_warehouses_name_uq ON warehouses(name)"
    )

    # 2) 种子 MAIN 仓（幂等）
    op.execute(
        "INSERT INTO warehouses(name) VALUES ('MAIN') ON CONFLICT (name) DO NOTHING"
    )


def downgrade() -> None:
    # 回滚仅删除 MAIN 这条种子与本迁移创建的索引
    op.execute("DELETE FROM warehouses WHERE name='MAIN'")
    op.execute("DROP INDEX IF EXISTS ix_warehouses_name_uq")
