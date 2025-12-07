"""po_lines_add_spec_and_uoms

Revision ID: adf4ec9eeef8
Revises: a655a322bc4f
Create Date: 2025-11-28 14:30:08.295364

为采购单行新增供应商视角字段：
- spec_text: 规格描述，如 “1.5kg*8袋”
- base_uom: 最小包装单位（袋 / 包 / 罐）
- purchase_uom: 采购单位（件 / 箱）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "adf4ec9eeef8"
down_revision: Union[str, Sequence[str], None] = "a655a322bc4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 行表增加规格 & 单位字段
    op.add_column(
        "purchase_order_lines",
        sa.Column("spec_text", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column("base_uom", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column("purchase_uom", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    # 回滚时逆序删除
    op.drop_column("purchase_order_lines", "purchase_uom")
    op.drop_column("purchase_order_lines", "base_uom")
    op.drop_column("purchase_order_lines", "spec_text")
