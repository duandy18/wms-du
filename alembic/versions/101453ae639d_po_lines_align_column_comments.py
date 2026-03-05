"""po_lines: align column comments

Revision ID: 101453ae639d
Revises: d11239f52d9c
Create Date: 2026-02-19 21:29:59.039299
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "101453ae639d"
down_revision: Union[str, Sequence[str], None] = "d11239f52d9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ✅ 对齐为当前模型期望的 comment

    op.alter_column(
        "purchase_order_lines",
        "units_per_case",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("1"),
        comment="换算因子：每 1 采购单位包含多少最小单位（>0）",
    )

    op.alter_column(
        "purchase_order_lines",
        "qty_ordered",
        existing_type=sa.Integer(),
        existing_nullable=False,
        comment="订购数量（采购单位口径，>0）",
    )

    op.alter_column(
        "purchase_order_lines",
        "qty_ordered_base",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment="订购数量（最小单位 base，事实字段）",
    )

    op.alter_column(
        "purchase_order_lines",
        "discount_amount",
        existing_type=sa.Numeric(14, 2),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment="整行减免金额（>=0）",
    )


def downgrade() -> None:
    # 🔙 回到旧 comment 状态

    op.alter_column(
        "purchase_order_lines",
        "discount_amount",
        existing_type=sa.Numeric(14, 2),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment="整行减免金额（>=0），行金额=qty_ordered_base*supply_price-discount_amount",
    )

    op.alter_column(
        "purchase_order_lines",
        "qty_ordered_base",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("0"),
        comment="订购数量（最小单位，事实字段）",
    )

    op.alter_column(
        "purchase_order_lines",
        "qty_ordered",
        existing_type=sa.Integer(),
        existing_nullable=False,
        comment=None,
    )

    op.alter_column(
        "purchase_order_lines",
        "units_per_case",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("1"),
        comment=None,
    )
