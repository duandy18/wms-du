"""phase m4 gov: drop reservations tables

Revision ID: a473195bb528
Revises: e69ea88d6243
Create Date: 2026-03-01 14:29:39.910416

治理阶段：reservations 预占概念已在系统中移除，仅残留测试数据/历史残影。
本迁移负责从 DB 结构层删除：
- reservations
- reservation_lines
- reservation_allocations

设计：
- CI-safe / 幂等：全部使用 IF EXISTS
- 删除顺序：先子表再父表；并使用 CASCADE 清理依赖索引/约束
- downgrade 不支持（避免猜测历史结构；且概念已移除）
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a473195bb528"
down_revision: Union[str, Sequence[str], None] = "e69ea88d6243"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 子表 -> 父表，避免依赖顺序问题；CASCADE 清理 FK/索引等残留。
    op.execute("DROP TABLE IF EXISTS public.reservation_allocations CASCADE;")
    op.execute("DROP TABLE IF EXISTS public.reservation_lines CASCADE;")
    op.execute("DROP TABLE IF EXISTS public.reservations CASCADE;")


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade not supported: reservations concept has been removed in Phase M-4 governance."
    )
