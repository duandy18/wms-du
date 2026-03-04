"""shipping_providers: drop legacy json pricing fields

Revision ID: cd98745db32a
Revises: 827b298d7b09
Create Date: 2026-03-03 17:38:42.680192
"""

from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "cd98745db32a"
down_revision: Union[str, Sequence[str], None] = "827b298d7b09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 删除历史遗留 JSON 字段（不再作为真相源）
    op.execute(
        """
        ALTER TABLE shipping_providers
        DROP COLUMN IF EXISTS pricing_model;
        """
    )

    op.execute(
        """
        ALTER TABLE shipping_providers
        DROP COLUMN IF EXISTS region_rules;
        """
    )


def downgrade() -> None:
    # 恢复字段（仅结构回滚，不恢复数据）
    op.execute(
        """
        ALTER TABLE shipping_providers
        ADD COLUMN pricing_model JSONB;
        """
    )

    op.execute(
        """
        ALTER TABLE shipping_providers
        ADD COLUMN region_rules JSONB;
        """
    )
