"""fix max_kg zero to null and enforce bracket range

Revision ID: b57f647699f1
Revises: b60b409dedab
Create Date: 2025-12-25 10:17:16.892404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b57f647699f1"
down_revision: Union[str, Sequence[str], None] = "b60b409dedab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1) 修历史脏数据：max_kg = 0 -> NULL（∞）
    op.execute(
        sa.text(
            """
            UPDATE shipping_provider_zone_brackets
            SET max_kg = NULL
            WHERE max_kg = 0
            """
        )
    )

    # 2) 加 CHECK 约束：max_kg 必须 NULL 或 > min_kg
    #    （同时隐含禁止 max_kg=0，因为 0 不可能 > min_kg 且 min_kg>=0）
    op.create_check_constraint(
        "ck_spzb_range_valid",
        "shipping_provider_zone_brackets",
        "max_kg IS NULL OR max_kg > min_kg",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 回滚：先删约束
    op.drop_constraint(
        "ck_spzb_range_valid",
        "shipping_provider_zone_brackets",
        type_="check",
    )

    # 回滚：把 NULL 还原为 0（不推荐业务上这么做，但保持可逆）
    op.execute(
        sa.text(
            """
            UPDATE shipping_provider_zone_brackets
            SET max_kg = 0
            WHERE max_kg IS NULL
            """
        )
    )
