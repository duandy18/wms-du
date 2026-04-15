"""procurement_add_po_no_to_purchase_orders

Revision ID: 65012e944c84
Revises: 0b2f772d3010
Create Date: 2026-04-13 11:06:07.200296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "65012e944c84"
down_revision: Union[str, Sequence[str], None] = "0b2f772d3010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1) 先加列，允许临时为空，便于回填历史数据
    op.add_column(
        "purchase_orders",
        sa.Column(
            "po_no",
            sa.String(length=64),
            nullable=True,
            comment="采购业务单号（如 PO-123）",
        ),
    )

    # 2) 回填历史数据：PO-{id}
    op.execute(
        """
        UPDATE purchase_orders
           SET po_no = 'PO-' || id::text
         WHERE po_no IS NULL
        """
    )

    # 3) 加唯一约束
    op.create_unique_constraint(
        "uq_purchase_orders_po_no",
        "purchase_orders",
        ["po_no"],
    )

    # 4) 收紧为 NOT NULL
    op.alter_column(
        "purchase_orders",
        "po_no",
        existing_type=sa.String(length=64),
        nullable=False,
        existing_comment="采购业务单号（如 PO-123）",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_purchase_orders_po_no",
        "purchase_orders",
        type_="unique",
    )

    op.drop_column("purchase_orders", "po_no")
