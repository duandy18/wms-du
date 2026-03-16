"""u10_simplify_shipping_record_reconciliations_to_diff_table

Revision ID: fbf656646dc8
Revises: d22e64d2684a
Create Date: 2026-03-16 18:18:58.649237
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fbf656646dc8"
down_revision: Union[str, Sequence[str], None] = "d22e64d2684a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    将 shipping_record_reconciliations 从“快照型对账表”
    简化为“差异处理表”。
    """

    # 1) 新增字段
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("tracking_no", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("adjust_amount", sa.Numeric(12, 2), nullable=True),
    )

    # 2) 从 shipping_records 回填 tracking_no
    op.execute(
        """
        UPDATE shipping_record_reconciliations r
        SET tracking_no = s.tracking_no
        FROM shipping_records s
        WHERE r.shipping_record_id = s.id
        """
    )

    # 3) tracking_no 改为 NOT NULL
    op.alter_column(
        "shipping_record_reconciliations",
        "tracking_no",
        existing_type=sa.String(length=128),
        nullable=False,
    )

    # 4) carrier_bill_item_id 改为 NOT NULL
    op.alter_column(
        "shipping_record_reconciliations",
        "carrier_bill_item_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    # 5) 删除旧索引
    op.drop_index(
        "ix_shipping_record_reconciliations_status",
        table_name="shipping_record_reconciliations",
    )

    # 6) 删除旧字段
    op.drop_column("shipping_record_reconciliations", "billing_weight_kg")
    op.drop_column("shipping_record_reconciliations", "freight_amount")
    op.drop_column("shipping_record_reconciliations", "surcharge_amount")
    op.drop_column("shipping_record_reconciliations", "cost_real")
    op.drop_column("shipping_record_reconciliations", "reconcile_status")
    op.drop_column("shipping_record_reconciliations", "reconciled_at")
    op.drop_column("shipping_record_reconciliations", "reconcile_note")

    # 7) 新索引
    op.create_index(
        "ix_shipping_record_reconciliations_tracking_no",
        "shipping_record_reconciliations",
        ["tracking_no"],
        unique=False,
    )


def downgrade() -> None:
    """
    回退为旧结构（快照型对账表）
    """

    # 1) 恢复旧字段
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("billing_weight_kg", sa.Numeric(10, 3), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("freight_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("surcharge_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("cost_real", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("reconcile_status", sa.String(length=32), nullable=False),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "shipping_record_reconciliations",
        sa.Column("reconcile_note", sa.String(length=512), nullable=True),
    )

    # 2) 恢复旧索引
    op.create_index(
        "ix_shipping_record_reconciliations_status",
        "shipping_record_reconciliations",
        ["reconcile_status"],
        unique=False,
    )

    # 3) 删除新索引
    op.drop_index(
        "ix_shipping_record_reconciliations_tracking_no",
        table_name="shipping_record_reconciliations",
    )

    # 4) carrier_bill_item_id 改回可空
    op.alter_column(
        "shipping_record_reconciliations",
        "carrier_bill_item_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    # 5) 删除新增字段
    op.drop_column("shipping_record_reconciliations", "adjust_amount")
    op.drop_column("shipping_record_reconciliations", "tracking_no")
