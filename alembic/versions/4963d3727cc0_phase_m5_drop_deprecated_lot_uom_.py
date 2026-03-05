"""phase m5: drop deprecated lot uom snapshots

Revision ID: 4963d3727cc0
Revises: a96e89d070b5
Create Date: 2026-03-01 16:12:34.682695

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4963d3727cc0"
down_revision: Union[str, Sequence[str], None] = "a96e89d070b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase M-5: unit_governance 二阶段（结构治理）
    - lots 不再承载单位快照（此前已完成停写/停读收口）
    - 物理删除退役列：
        * item_base_uom_snapshot
        * item_purchase_ratio_snapshot
        * item_purchase_uom_snapshot
    - 同步删除依赖约束：
        * ck_lots_item_purchase_ratio_ge_1_snapshot
    """
    # 显式 drop（不赌数据库隐式级联行为）
    op.drop_constraint(
        "ck_lots_item_purchase_ratio_ge_1_snapshot",
        "lots",
        type_="check",
    )

    # drop columns（从依赖最少的开始）
    op.drop_column("lots", "item_purchase_uom_snapshot")
    op.drop_column("lots", "item_purchase_ratio_snapshot")
    op.drop_column("lots", "item_base_uom_snapshot")


def downgrade() -> None:
    """
    回滚：恢复列与约束（注意：历史数据无法自动恢复，这是退役列的预期代价）
    """
    op.add_column("lots", sa.Column("item_base_uom_snapshot", sa.String(length=8), nullable=True))
    op.add_column("lots", sa.Column("item_purchase_ratio_snapshot", sa.Integer(), nullable=True))
    op.add_column("lots", sa.Column("item_purchase_uom_snapshot", sa.String(length=16), nullable=True))

    op.create_check_constraint(
        "ck_lots_item_purchase_ratio_ge_1_snapshot",
        "lots",
        "(item_purchase_ratio_snapshot IS NULL OR item_purchase_ratio_snapshot >= 1)",
    )
