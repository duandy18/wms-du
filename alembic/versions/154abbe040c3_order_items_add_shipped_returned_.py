"""order_items_add_shipped_returned_counters

Revision ID: 154abbe040c3
Revises: 1cc5f038f4bc
Create Date: 2025-11-29 21:26:05.940889
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '154abbe040c3'
down_revision: Union[str, Sequence[str], None] = '1cc5f038f4bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add shipped_qty / returned_qty to order_items.

    逻辑：
    - server_default="0" 用来确保旧数据迁移不会因 NOT NULL 报错；
    - 紧接着 alter_column 去掉 server_default；
    - 与 ORM 的字段定义完全对齐。
    """

    # -- 添加列：shipped_qty --
    op.add_column(
        "order_items",
        sa.Column(
            "shipped_qty",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # -- 添加列：returned_qty --
    op.add_column(
        "order_items",
        sa.Column(
            "returned_qty",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # -- 清除 server_default，避免未来插入依赖默认值 --
    op.alter_column("order_items", "shipped_qty", server_default=None)
    op.alter_column("order_items", "returned_qty", server_default=None)


def downgrade() -> None:
    """Drop the two counters."""
    op.drop_column("order_items", "returned_qty")
    op.drop_column("order_items", "shipped_qty")
