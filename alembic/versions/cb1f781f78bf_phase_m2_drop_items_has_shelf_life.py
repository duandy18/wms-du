"""phase_m2_drop_items_has_shelf_life

Revision ID: cb1f781f78bf
Revises: f3724d57f464
Create Date: 2026-02-28 16:28:28.087215

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cb1f781f78bf"
down_revision: Union[str, Sequence[str], None] = "f3724d57f464"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    删除 items.has_shelf_life（镜像字段）。

    原因：
    - expiry_policy 已成为唯一规则真相源
    - has_shelf_life 只是镜像字段
    - DB CHECK 已锁死两者一致
    """

    # 1️⃣ 删除相关 CHECK 约束（依赖 has_shelf_life）
    op.drop_constraint(
        "ck_items_has_shelf_life_matches_expiry_policy",
        "items",
        type_="check",
    )

    op.drop_constraint(
        "ck_items_shelf_life_params_only_when_enabled",
        "items",
        type_="check",
    )

    # 2️⃣ 删除列
    op.drop_column("items", "has_shelf_life")


def downgrade() -> None:
    """
    回退：恢复 has_shelf_life 列与相关约束
    """

    # 1️⃣ 恢复列
    op.add_column(
        "items",
        sa.Column(
            "has_shelf_life",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 2️⃣ 恢复约束
    op.create_check_constraint(
        "ck_items_has_shelf_life_matches_expiry_policy",
        "items",
        "has_shelf_life = (expiry_policy = 'REQUIRED')",
    )

    op.create_check_constraint(
        "ck_items_shelf_life_params_only_when_enabled",
        "items",
        "has_shelf_life = true OR shelf_life_value IS NULL AND shelf_life_unit IS NULL",
    )
