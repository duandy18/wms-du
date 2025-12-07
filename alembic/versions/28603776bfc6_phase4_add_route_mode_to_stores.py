"""phase4: add route_mode to stores

Revision ID: 28603776bfc6
Revises: ee4f8beeff56
Create Date: 2025-11-16 19:54:02.943404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "28603776bfc6"
down_revision: Union[str, Sequence[str], None] = "ee4f8beeff56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 为 stores 增加 route_mode 字段，用于控制多仓路由策略。
    #
    # 约定：
    #   - 'FALLBACK'（默认）：当前逻辑，主仓优先，主仓不够时允许备仓兜底；
    #   - 'STRICT_TOP'：只允许主仓，主仓不够视为“无仓可履约”，不使用备仓。
    #
    # 这里设置 server_default='FALLBACK'，确保已有数据不会出现 NULL。
    op.add_column(
        "stores",
        sa.Column("route_mode", sa.String(length=32), nullable=False, server_default="FALLBACK"),
    )

    # 如果你以后想去掉默认值，可以在后续 migration 里单独执行：
    # op.alter_column("stores", "route_mode", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stores", "route_mode")
