"""merge all parallel heads to fix cycle

Revision ID: 7f_merge_cycle_fix
Revises:
    1088800f816e,
    1223487447f9,
    1f9e5c2b8a11,
    2a01baddb001,
    2a01baddb002,
    3a_fix_sqlite_inline_pks,
    bdc33e80391a
Create Date: 2025-10-12 21:08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa  # noqa

# revision identifiers, used by Alembic.
revision: str = "7f_merge_cycle_fix"
# 这里把形成环的一组版本全部作为 down_revision 元组（merge 语义）
down_revision: str | Sequence[str] | None = (
    "1088800f816e",
    "1223487447f9",
    "1f9e5c2b8a11",
    "2a01baddb001",
    "2a01baddb002",
    "3a_fix_sqlite_inline_pks",
    "bdc33e80391a",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # merge 版本：不做任何 DDL，只是把多条并行链并为一头
    pass


def downgrade() -> None:
    # 反向拆分为多头（仍不做任何 DDL）
    pass
