"""receipt_lines_add_item_snap_fields

Revision ID: d959e5cde055
Revises: 7de1ab7377a4
Create Date: 2026-01-13 15:38:31.835564

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d959e5cde055"
down_revision: Union[str, Sequence[str], None] = "7de1ab7377a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("inbound_receipt_lines", sa.Column("category", sa.String(length=64), nullable=True))
    op.add_column("inbound_receipt_lines", sa.Column("spec_text", sa.String(length=255), nullable=True))
    op.add_column("inbound_receipt_lines", sa.Column("base_uom", sa.String(length=32), nullable=True))
    op.add_column("inbound_receipt_lines", sa.Column("purchase_uom", sa.String(length=32), nullable=True))

    # 索引：提升 items 报表 / 对账查询性能（如已存在会报错，必要时可删除这两行再升级）
    op.create_index("ix_inbound_receipt_lines_item_id", "inbound_receipt_lines", ["item_id"], unique=False)
    op.create_index("ix_inbound_receipt_lines_po_line_id", "inbound_receipt_lines", ["po_line_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_inbound_receipt_lines_po_line_id", table_name="inbound_receipt_lines")
    op.drop_index("ix_inbound_receipt_lines_item_id", table_name="inbound_receipt_lines")

    op.drop_column("inbound_receipt_lines", "purchase_uom")
    op.drop_column("inbound_receipt_lines", "base_uom")
    op.drop_column("inbound_receipt_lines", "spec_text")
    op.drop_column("inbound_receipt_lines", "category")
