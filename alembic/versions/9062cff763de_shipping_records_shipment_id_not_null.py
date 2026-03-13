"""shipping_records shipment_id not null

Revision ID: 9062cff763de
Revises: a69c81df73c8
Create Date: 2026-03-13 13:34:31.391062
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9062cff763de"
down_revision: Union[str, Sequence[str], None] = "a69c81df73c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 防止误操作：必须没有 NULL
    null_count = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM shipping_records
            WHERE shipment_id IS NULL
            """
        )
    ).scalar_one()

    if int(null_count or 0) != 0:
        raise RuntimeError(
            f"Cannot set shipping_records.shipment_id NOT NULL: "
            f"{int(null_count)} rows still have shipment_id IS NULL"
        )

    # 防止 orphan projection
    orphan_count = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM shipping_records sr
            LEFT JOIN transport_shipments ts
              ON ts.id = sr.shipment_id
            WHERE sr.shipment_id IS NOT NULL
              AND ts.id IS NULL
            """
        )
    ).scalar_one()

    if int(orphan_count or 0) != 0:
        raise RuntimeError(
            f"Cannot set shipping_records.shipment_id NOT NULL: "
            f"{int(orphan_count)} orphan rows found"
        )

    op.alter_column(
        "shipping_records",
        "shipment_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "shipping_records",
        "shipment_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
