"""drop platform_order_lines platform_sku_id

Revision ID: 0c45c147d9c8
Revises: a144b9a4a774
Create Date: 2026-02-10 10:51:38.700908
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0c45c147d9c8"
down_revision: Union[str, Sequence[str], None] = "a144b9a4a774"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Phase N+2 · 最终收口：
    # 删除 platform_order_lines 中的 legacy 字段 platform_sku_id
    op.drop_column("platform_order_lines", "platform_sku_id")


def downgrade() -> None:
    # 回滚：恢复 legacy 字段（保持 nullable，避免历史数据回填问题）
    op.add_column(
        "platform_order_lines",
        sa.Column("platform_sku_id", sa.String(length=200), nullable=True),
    )
