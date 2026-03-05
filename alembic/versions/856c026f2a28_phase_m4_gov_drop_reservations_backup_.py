"""phase m4 gov: drop reservations backup table

Revision ID: 856c026f2a28
Revises: a473195bb528
Create Date: 2026-03-01 14:33:10.856922

治理阶段：删除历史遗留的 reservations 备份表：
- pick_task_line_reservations_backup_20251109

设计：
- CI-safe / 幂等：使用 IF EXISTS
- downgrade 不支持（概念已移除，避免误复活）
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "856c026f2a28"
down_revision: Union[str, Sequence[str], None] = "a473195bb528"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS public.pick_task_line_reservations_backup_20251109;"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade not supported: reservations backup table removed in Phase M-4 governance."
    )
