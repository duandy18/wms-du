"""route-c: add city-split provinces switch

Revision ID: a42bd0f65d65
Revises: bf1cdd998bda
Create Date: 2026-01-18 19:35:41.057282
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a42bd0f65d65"
down_revision: Union[str, Sequence[str], None] = "bf1cdd998bda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    新增：省份“按城市细分”开关表

    语义：
    - 表中出现的省份，表示该省不再使用省级服务仓规则
    - 该省的订单必须按城市规则命中服务仓
    - 若城市未配置，则明确 NO_SERVICE_WAREHOUSE（Route C 显式阻断）
    """
    op.create_table(
        "warehouse_service_city_split_provinces",
        sa.Column("province_code", sa.String(length=32), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_wh_city_split_provinces_created_at",
        "warehouse_service_city_split_provinces",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wh_city_split_provinces_created_at",
        table_name="warehouse_service_city_split_provinces",
    )
    op.drop_table("warehouse_service_city_split_provinces")
