"""phase m5: drop po line display-only uom columns

Revision ID: cdf186f509e7
Revises: 26bc42811b4b
Create Date: 2026-03-01 16:38:34.179292

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cdf186f509e7"
down_revision: Union[str, Sequence[str], None] = "26bc42811b4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase M-5：unit_governance 二阶段
    - PO 行的 display-only 字符串单位字段进入硬删除：
        * purchase_order_lines.base_uom
        * purchase_order_lines.uom_snapshot
    - 事实字段口径保持不变：
        * purchase_uom_id_snapshot / purchase_ratio_to_base_snapshot
        * qty_ordered_input / qty_ordered_base
    """
    op.drop_column("purchase_order_lines", "base_uom")
    op.drop_column("purchase_order_lines", "uom_snapshot")


def downgrade() -> None:
    """
    回滚：恢复列（注意：历史值无法自动恢复，这是硬删除的预期代价）
    """
    op.add_column("purchase_order_lines", sa.Column("base_uom", sa.String(length=32), nullable=True))
    op.add_column("purchase_order_lines", sa.Column("uom_snapshot", sa.String(length=32), nullable=False))
