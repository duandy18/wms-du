"""store_warehouse store fk restrict (no cascade)

Revision ID: abe0b1aa9a30
Revises: f1c02901fb50
Create Date: 2025-12-13 11:41:19.139618

目标（Phase 3 延展一致性）：
- store_warehouse 是“配置事实”，不允许删除 store 时隐式级联删除绑定记录
- 将 store_warehouse_store_id_fkey：ON DELETE CASCADE -> ON DELETE RESTRICT
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "abe0b1aa9a30"
down_revision: Union[str, Sequence[str], None] = "f1c02901fb50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 删除旧外键（CASCADE）
    op.drop_constraint(
        "store_warehouse_store_id_fkey",
        "store_warehouse",
        type_="foreignkey",
    )

    # 2) 重建为 RESTRICT（禁止隐式抹除配置事实）
    op.create_foreign_key(
        "store_warehouse_store_id_fkey",
        "store_warehouse",
        "stores",
        ["store_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # 回滚：恢复为 CASCADE（不推荐，但保持可回滚）
    op.drop_constraint(
        "store_warehouse_store_id_fkey",
        "store_warehouse",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "store_warehouse_store_id_fkey",
        "store_warehouse",
        "stores",
        ["store_id"],
        ["id"],
        ondelete="CASCADE",
    )
