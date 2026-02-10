"""platform_order_lines add filled_code and backfill from platform_sku_id

Revision ID: a144b9a4a774
Revises: 7df9cd0ee9b1
Create Date: 2026-02-10 10:28:34.604959
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a144b9a4a774"
down_revision: Union[str, Sequence[str], None] = "7df9cd0ee9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 新增 filled_code 字段（暂时允许 NULL，代码切换完成后再收紧）
    op.add_column(
        "platform_order_lines",
        sa.Column("filled_code", sa.Text(), nullable=True),
    )

    # 2) 回填历史数据：
    #    将 legacy 的 platform_sku_id 拷贝到 filled_code
    #    - 只在 filled_code 为空时回填
    #    - 忽略 NULL / 空字符串，避免制造脏数据
    op.execute(
        """
        UPDATE platform_order_lines
           SET filled_code = platform_sku_id
         WHERE filled_code IS NULL
           AND platform_sku_id IS NOT NULL
           AND btrim(platform_sku_id) <> '';
        """
    )


def downgrade() -> None:
    # 回滚只删除新加字段，不动 legacy 列
    op.drop_column("platform_order_lines", "filled_code")
