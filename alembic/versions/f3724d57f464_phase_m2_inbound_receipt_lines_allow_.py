"""phase_m2 inbound_receipt_lines allow null lot_id for draft and add batch_code_input

Revision ID: f3724d57f464
Revises: 0a416b5c1b27
Create Date: 2026-02-28 16:12:23.660968

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3724d57f464"
down_revision: Union[str, Sequence[str], None] = "0a416b5c1b27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Route B:

    1) 允许 draft 阶段 lot_id 为空
    2) 移除复合 FK (lot_id, warehouse_id, item_id)
    3) 新增 batch_code 输入字段
    """

    # 1️⃣ 新增 batch_code 列（输入标签）
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("batch_code", sa.String(length=64), nullable=True),
    )

    # 2️⃣ 删除复合 FK（draft 允许 lot_id NULL）
    op.drop_constraint(
        "fk_inbound_receipt_lines_lot_dims",
        "inbound_receipt_lines",
        type_="foreignkey",
    )

    # 3️⃣ lot_id 改为 nullable
    op.alter_column(
        "inbound_receipt_lines",
        "lot_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    """
    回退为旧形态：

    - lot_id 恢复 NOT NULL
    - 恢复复合 FK
    - 删除 batch_code
    """

    # 1️⃣ lot_id 恢复 NOT NULL
    op.alter_column(
        "inbound_receipt_lines",
        "lot_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # 2️⃣ 恢复复合 FK
    op.create_foreign_key(
        "fk_inbound_receipt_lines_lot_dims",
        "inbound_receipt_lines",
        "lots",
        ["lot_id", "warehouse_id", "item_id"],
        ["id", "warehouse_id", "item_id"],
        ondelete="RESTRICT",
    )

    # 3️⃣ 删除 batch_code
    op.drop_column("inbound_receipt_lines", "batch_code")
