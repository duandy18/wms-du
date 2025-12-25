"""add_uq_sp_zone_brackets_range

Revision ID: 4ec12f14eb40
Revises: 7c9cc1182cf6
Create Date: 2025-12-20 17:49:05.520091

目的：
- 防止同一个 zone 下出现重复的重量段 bracket（min_kg/max_kg 相同）
- max_kg 允许 NULL（表示 infinity），所以唯一约束用表达式索引：
  UNIQUE(zone_id, min_kg, COALESCE(max_kg, 999999.000))
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4ec12f14eb40"
down_revision: Union[str, Sequence[str], None] = "7c9cc1182cf6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_zone_brackets"
IDX_UQ = "uq_spzb_zone_min_max_coalesced"


def upgrade() -> None:
    # 若历史数据里仍存在重复区间，这里会失败（duplicate key），这正是我们要的防呆闸门。
    # 失败时用：
    #   SELECT zone_id, min_kg, max_kg, COUNT(*), ARRAY_AGG(id ORDER BY id)
    #   FROM shipping_provider_zone_brackets
    #   GROUP BY zone_id, min_kg, max_kg
    #   HAVING COUNT(*) > 1;
    # 找出重复后清理（保留一条，删除其余）再重跑 upgrade。
    op.create_index(
        IDX_UQ,
        TABLE,
        [
            sa.text("zone_id"),
            sa.text("min_kg"),
            sa.text("COALESCE(max_kg, 999999.000)"),
        ],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(IDX_UQ, table_name=TABLE)
