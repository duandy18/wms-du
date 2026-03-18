"""shipping_records_add_estimated_breakdown_dims_sender

Revision ID: 7053c668a3cb
Revises: 4d26a4dc950a
Create Date: 2026-03-18 20:51:26.257055

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7053c668a3cb"
down_revision: Union[str, Sequence[str], None] = "4d26a4dc950a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 费用拆分
    op.add_column(
        "shipping_records",
        sa.Column("freight_estimated", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("surcharge_estimated", sa.Numeric(12, 2), nullable=True),
    )

    # 尺寸
    op.add_column(
        "shipping_records",
        sa.Column("length_cm", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("width_cm", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("height_cm", sa.Numeric(10, 2), nullable=True),
    )

    # 寄件人
    op.add_column(
        "shipping_records",
        sa.Column("sender", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column("shipping_records", "sender")
    op.drop_column("shipping_records", "height_cm")
    op.drop_column("shipping_records", "width_cm")
    op.drop_column("shipping_records", "length_cm")
    op.drop_column("shipping_records", "surcharge_estimated")
    op.drop_column("shipping_records", "freight_estimated")
