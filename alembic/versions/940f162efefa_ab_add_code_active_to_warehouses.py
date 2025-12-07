"""ab_add_code_active_to_warehouses

Revision ID: 940f162efefa
Revises: 29480788f1e9
Create Date: 2025-11-27 07:59:32.326155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "940f162efefa"
down_revision: Union[str, Sequence[str], None] = "29480788f1e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add code & active columns to warehouses."""
    # code: 仓库编码，可空，但全局唯一
    op.add_column(
        "warehouses",
        sa.Column("code", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_warehouses_code",
        "warehouses",
        ["code"],
    )

    # active: 是否启用，默认 TRUE
    op.add_column(
        "warehouses",
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
    )

    # 把历史数据全部标记为启用
    op.execute("UPDATE warehouses SET active = TRUE")


def downgrade() -> None:
    """Downgrade schema: drop code & active columns from warehouses."""
    # 注意顺序：先删约束，再删列
    op.drop_constraint("uq_warehouses_code", "warehouses", type_="unique")
    op.drop_column("warehouses", "code")
    op.drop_column("warehouses", "active")
