"""phase m4 gov: drop channel_reserve_ops backup table

Revision ID: c1c3f22bb2ac
Revises: 856c026f2a28
Create Date: 2026-03-01 14:37:34.137479

治理阶段：删除历史遗留的 channel_reserve_ops 备份表：
- channel_reserve_ops_backup_20251109

设计：
- CI-safe / 幂等：使用 IF EXISTS
- downgrade 不支持（治理清理不允许误回滚复活）
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c1c3f22bb2ac"
down_revision: Union[str, Sequence[str], None] = "856c026f2a28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS public.channel_reserve_ops_backup_20251109 CASCADE;"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade not supported: channel_reserve_ops backup removed in Phase M-4 governance."
    )
