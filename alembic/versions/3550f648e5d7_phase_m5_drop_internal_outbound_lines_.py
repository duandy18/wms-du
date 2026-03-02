"""phase m5: drop internal_outbound_lines.uom

Revision ID: 3550f648e5d7
Revises: bd9228ed4d6a
Create Date: 2026-03-01 17:37:07.618322

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3550f648e5d7"
down_revision: Union[str, Sequence[str], None] = "bd9228ed4d6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase M-5：
    - internal_outbound_lines.uom 已停止读写（应用层收口完成）
    - 物理删除列，避免单位语义再分叉
    """
    op.drop_column("internal_outbound_lines", "uom")


def downgrade() -> None:
    """
    回滚：恢复列（text，可空）
    注意：历史值无法自动恢复（硬删列的预期代价）
    """
    op.add_column("internal_outbound_lines", sa.Column("uom", sa.Text(), nullable=True))
