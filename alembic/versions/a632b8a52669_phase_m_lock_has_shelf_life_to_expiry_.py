"""phase_m: lock has_shelf_life to expiry_policy (no dual truth)

Revision ID: a632b8a52669
Revises: 394bddb7b16c
Create Date: 2026-02-27 10:48:58.771389

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a632b8a52669"
down_revision: Union[str, Sequence[str], None] = "394bddb7b16c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    彻底消灭 items 上的“双轨规则”：
    has_shelf_life 必须等于 (expiry_policy == 'REQUIRED')

    从此：
    - expiry_policy 是唯一规则源
    - has_shelf_life 仅作为派生字段存在
    """

    # 1️⃣ 先对齐历史数据
    op.execute(
        """
UPDATE items
SET has_shelf_life = (expiry_policy = 'REQUIRED'::expiry_policy);
"""
    )

    # 2️⃣ 加封板约束：禁止未来出现双真相源
    op.create_check_constraint(
        "ck_items_has_shelf_life_matches_expiry_policy",
        "items",
        "has_shelf_life = (expiry_policy = 'REQUIRED'::expiry_policy)",
    )


def downgrade() -> None:
    """
    反向迁移：移除一致性约束（测试环境允许）
    """

    op.drop_constraint(
        "ck_items_has_shelf_life_matches_expiry_policy",
        "items",
        type_="check",
    )
