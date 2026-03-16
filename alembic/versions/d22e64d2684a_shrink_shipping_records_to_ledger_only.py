"""shrink shipping_records to ledger only

Revision ID: d22e64d2684a
Revises: 245b131a859b
Create Date: 2026-03-16 15:55:01.074539
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d22e64d2684a"
down_revision: Union[str, Sequence[str], None] = "245b131a859b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    shipping_records 收口为“物流台帐表”：
    - 删除 shipment_id 外键
    - 删除 shipment_id 索引
    - 删除 shipment_id 列
    """

    op.drop_constraint(
        "fk_shipping_records_shipment_id",
        "shipping_records",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_shipping_records_shipment_id",
        table_name="shipping_records",
    )

    op.drop_column(
        "shipping_records",
        "shipment_id",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade not supported: shipping_records.shipment_id was removed permanently."
    )
