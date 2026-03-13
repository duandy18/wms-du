"""shipping_records shipment_id unique

Revision ID: 1c3a5672cfba
Revises: 9062cff763de
Create Date: 2026-03-13 13:41:49.037997
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c3a5672cfba"
down_revision: Union[str, Sequence[str], None] = "9062cff763de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 防止脏数据：检查 shipment_id 是否重复
    dup_count = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM (
                SELECT shipment_id
                FROM shipping_records
                GROUP BY shipment_id
                HAVING COUNT(*) > 1
            ) t
            """
        )
    ).scalar_one()

    if int(dup_count or 0) != 0:
        raise RuntimeError(
            f"Cannot create unique index on shipping_records.shipment_id: "
            f"{int(dup_count)} duplicated shipment_id groups found"
        )

    op.create_index(
        "uq_shipping_records_shipment_id",
        "shipping_records",
        ["shipment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_shipping_records_shipment_id",
        table_name="shipping_records",
    )
