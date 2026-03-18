"""billing: add unique constraint for carrier_code + tracking_no

Revision ID: bd368177ca26
Revises: 519ebdffcf18
Create Date: 2026-03-18 12:20:27.185814

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'bd368177ca26'
down_revision: Union[str, Sequence[str], None] = '519ebdffcf18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ⚠️ 第一步：清理重复数据（必须，否则 unique 会失败）
    op.execute(
        """
        DELETE FROM carrier_bill_items a
        USING carrier_bill_items b
        WHERE a.id < b.id
          AND a.carrier_code = b.carrier_code
          AND a.tracking_no = b.tracking_no;
        """
    )

    # ⚠️ 第二步：添加唯一约束（核心）
    op.create_unique_constraint(
        "uq_carrier_bill_items_carrier_tracking",
        "carrier_bill_items",
        ["carrier_code", "tracking_no"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "uq_carrier_bill_items_carrier_tracking",
        "carrier_bill_items",
        type_="unique",
    )
