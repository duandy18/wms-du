"""phase_m3 drop items.case_ratio and case_uom

Revision ID: a93d20ebd122
Revises: 2c38424c780a
Create Date: 2026-03-01 01:12:28.330400

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a93d20ebd122"
down_revision: Union[str, Sequence[str], None] = "2c38424c780a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase M-3：
    - items.case_ratio / case_uom 已在前一 revision 中通过 CHECK 约束封死写入
    - 本次做最终结构减法：物理删除列
    """

    # 删除列（相关 CHECK 会自动一并移除）
    op.drop_column("items", "case_ratio")
    op.drop_column("items", "case_uom")


def downgrade() -> None:
    """
    回滚：
    - 恢复列定义（不恢复历史数据）
    - 不恢复 ck_items_case_fields_must_be_null 约束
    """

    op.add_column(
        "items",
        sa.Column(
            "case_ratio",
            sa.Integer(),
            nullable=True,
            comment="箱装换算倍率（整数）；1 case_uom = case_ratio × uom（最小单位）；允许为空（未治理）",
        ),
    )

    op.add_column(
        "items",
        sa.Column(
            "case_uom",
            sa.String(length=16),
            nullable=True,
            comment="箱装单位名（展示/输入偏好），如“箱”；允许为空（未治理）",
        ),
    )
