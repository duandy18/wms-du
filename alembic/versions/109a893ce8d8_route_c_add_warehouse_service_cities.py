"""
route_c_add_warehouse_service_cities

Revision ID: 109a893ce8d8
Revises: a42bd0f65d65
Create Date: 2026-01-19 16:31:09.033753
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "109a893ce8d8"
down_revision: Union[str, Sequence[str], None] = "a42bd0f65d65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "warehouse_service_cities"
_UX_CITY = "ux_warehouse_service_cities_city_code"
_IX_WID = "ix_warehouse_service_cities_warehouse_id"


def upgrade() -> None:
    """
    新增：warehouse_service_cities

    Route C 合同：
    - city_code -> 唯一 service warehouse
    - 不存在 fallback / priority / store 维度

    幂等策略（为解决 DEV 环境可能已存在同名表）：
    - 表存在则跳过 create_table
    - 索引使用 IF NOT EXISTS 确保可重复执行
    """
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column(
                "warehouse_id",
                sa.BigInteger(),
                sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("city_code", sa.String(length=64), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    # 索引：用 IF NOT EXISTS 处理“已存在”的情况（Postgres）
    op.execute(
        sa.text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {_UX_CITY} ON {_TABLE} (city_code)"
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS {_IX_WID} ON {_TABLE} (warehouse_id)"
        )
    )


def downgrade() -> None:
    """
    回滚：删除 warehouse_service_cities

    注意：如果表本来就存在（历史遗留/手工创建），降级会删除它。
    这是迁移语义的正常代价；若你希望 DEV 永不删除，可只在测试库跑 downgrade。
    """
    bind = op.get_bind()
    insp = inspect(bind)

    # 先 drop index（存在才 drop）
    if insp.has_table(_TABLE):
        op.execute(sa.text(f"DROP INDEX IF EXISTS {_IX_WID}"))
        op.execute(sa.text(f"DROP INDEX IF EXISTS {_UX_CITY}"))
        op.drop_table(_TABLE)
