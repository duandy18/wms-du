"""u11_set_shipping_reconciliation_bill_item_not_null

Revision ID: 28a7dbaef752
Revises: fbf656646dc8
Create Date: 2026-03-16 18:29:24.082804
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "28a7dbaef752"
down_revision: Union[str, Sequence[str], None] = "fbf656646dc8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    新语义下：
    shipping_record_reconciliations 只记录
    已匹配且存在差异的运单。

    因此 carrier_bill_item_id 必须存在。
    """

    # 1 清理历史脏数据
    op.execute(
        """
        DELETE FROM shipping_record_reconciliations
        WHERE carrier_bill_item_id IS NULL
        """
    )

    # 2 设置 NOT NULL
    op.alter_column(
        "shipping_record_reconciliations",
        "carrier_bill_item_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )


def downgrade() -> None:
    """
    回滚为可空
    """

    op.alter_column(
        "shipping_record_reconciliations",
        "carrier_bill_item_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
