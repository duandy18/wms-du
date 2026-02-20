"""chore(po): sync supplier column comments

Revision ID: b2aa0c90d971
Revises: b1130f45fec2
Create Date: 2026-02-20 11:29:54.333701

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2aa0c90d971"
down_revision: Union[str, Sequence[str], None] = "b1130f45fec2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    同步 purchase_orders.supplier_id / supplier_name 的列注释，
    解决 alembic-check 检测到的 comment drift。
    """

    op.alter_column(
        "purchase_orders",
        "supplier_id",
        existing_type=sa.Integer(),
        comment="FK → suppliers.id（必填）",
    )

    op.alter_column(
        "purchase_orders",
        "supplier_name",
        existing_type=sa.String(length=255),
        comment="下单时的供应商名称快照（必填，通常来自 suppliers.name）",
    )


def downgrade() -> None:
    """
    回滚为旧注释（与历史数据库口径一致）
    """

    op.alter_column(
        "purchase_orders",
        "supplier_id",
        existing_type=sa.Integer(),
        comment="FK → suppliers.id，可为空",
    )

    op.alter_column(
        "purchase_orders",
        "supplier_name",
        existing_type=sa.String(length=255),
        comment="下单时的供应商名称快照，通常来自 suppliers.name",
    )
