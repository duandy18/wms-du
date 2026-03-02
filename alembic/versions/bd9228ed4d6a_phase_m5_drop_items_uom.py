"""phase m5: drop items.uom

Revision ID: bd9228ed4d6a
Revises: cdf186f509e7
Create Date: 2026-03-01 17:07:53.562643

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bd9228ed4d6a"
down_revision: Union[str, Sequence[str], None] = "cdf186f509e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase M-5：unit_governance 二阶段
    - 彻底移除 items.uom，避免单位“双主权”
    - base_uom 真相源 = item_uoms.is_base=true
    """
    op.drop_column("items", "uom")


def downgrade() -> None:
    """
    回滚：恢复 items.uom（legacy）
    注意：回滚后默认值为 'PCS'，历史值无法自动恢复（硬删列的预期代价）
    """
    op.add_column(
        "items",
        sa.Column(
            "uom",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'PCS'::character varying"),
        ),
    )
