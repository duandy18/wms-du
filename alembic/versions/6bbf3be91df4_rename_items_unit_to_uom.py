"""rename items.unit to uom

Revision ID: 6bbf3be91df4
Revises: b93448767675
Create Date: 2026-02-21 23:05:16.057696
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6bbf3be91df4"
down_revision: Union[str, Sequence[str], None] = "b93448767675"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Rename items.unit -> items.uom

    语义收敛：
    - unit 更名为 uom（唯一事实单位）
    - 不改变数据
    - 不改变默认值
    - 不改变约束
    """
    op.alter_column("items", "unit", new_column_name="uom")


def downgrade() -> None:
    """
    Rollback: items.uom -> items.unit
    """
    op.alter_column("items", "uom", new_column_name="unit")
