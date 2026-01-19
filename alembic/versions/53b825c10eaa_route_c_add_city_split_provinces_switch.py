"""
route_c_add_city_split_provinces_switch

Revision ID: 53b825c10eaa
Revises: 109a893ce8d8
Create Date: 2026-01-19 16:31:09.387220
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "53b825c10eaa"
down_revision: Union[str, Sequence[str], None] = "109a893ce8d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "warehouse_service_city_split_provinces"


def upgrade() -> None:
    """
    新增：warehouse_service_city_split_provinces

    Route C 合同：
    - 出现在该表中的 province_code => 该省启用“按城市配置”
    - province 默认 service warehouse 冻结失效

    幂等策略：表存在则跳过 create_table
    """
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table(_TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("province_code", sa.String(length=64), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """
    回滚：删除 warehouse_service_city_split_provinces
    """
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table(_TABLE):
        op.drop_table(_TABLE)
