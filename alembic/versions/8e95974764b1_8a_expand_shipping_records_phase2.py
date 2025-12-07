"""8a_expand_shipping_records_phase2

Revision ID: 8e95974764b1
Revises: 0a720839f121
Create Date: 2025-12-04 10:53:15.023635

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e95974764b1"
down_revision: Union[str, Sequence[str], None] = "0a720839f121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: expand shipping_records to Phase 2."""
    # 冗余承运商名称
    op.add_column(
        "shipping_records",
        sa.Column("carrier_name", sa.String(length=128), nullable=True),
    )
    # 运单号 / 电子面单号
    op.add_column(
        "shipping_records",
        sa.Column("tracking_no", sa.String(length=128), nullable=True),
    )
    # 实际称重毛重
    op.add_column(
        "shipping_records",
        sa.Column("gross_weight_kg", sa.Numeric(10, 3), nullable=True),
    )
    # 包材重量
    op.add_column(
        "shipping_records",
        sa.Column("packaging_weight_kg", sa.Numeric(10, 3), nullable=True),
    )
    # 实际送达时间
    op.add_column(
        "shipping_records",
        sa.Column("delivery_time", sa.DateTime(timezone=True), nullable=True),
    )
    # 状态：IN_TRANSIT / DELIVERED / LOST / RETURNED 等
    op.add_column(
        "shipping_records",
        sa.Column("status", sa.String(length=32), nullable=True),
    )
    # 错误码 / 错误信息
    op.add_column(
        "shipping_records",
        sa.Column("error_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("error_message", sa.String(length=512), nullable=True),
    )

    # 运单号索引，方便按运单号查账
    op.create_index(
        "ix_shipping_records_tracking_no",
        "shipping_records",
        ["tracking_no"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema: rollback Phase 2 columns."""
    op.drop_index("ix_shipping_records_tracking_no", table_name="shipping_records")
    op.drop_column("shipping_records", "error_message")
    op.drop_column("shipping_records", "error_code")
    op.drop_column("shipping_records", "status")
    op.drop_column("shipping_records", "delivery_time")
    op.drop_column("shipping_records", "packaging_weight_kg")
    op.drop_column("shipping_records", "gross_weight_kg")
    op.drop_column("shipping_records", "tracking_no")
    op.drop_column("shipping_records", "carrier_name")
