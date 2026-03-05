"""phase m4 gov: drop channel_reserved_idem

Revision ID: 5a34cd869461
Revises: c1c3f22bb2ac
Create Date: 2026-03-01 14:39:38.428785

治理阶段：删除历史遗留的 channel_reserved_idem 表。
该表已无运行期引用，仅残留历史数据。
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5a34cd869461"
down_revision: Union[str, Sequence[str], None] = "c1c3f22bb2ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 幂等删除，避免不同环境 drift 报错
    op.execute("DROP TABLE IF EXISTS public.channel_reserved_idem CASCADE;")


def downgrade() -> None:
    # 治理清理不支持回滚复活
    raise RuntimeError(
        "Downgrade not supported: channel_reserved_idem removed in Phase M-4 governance."
    )
