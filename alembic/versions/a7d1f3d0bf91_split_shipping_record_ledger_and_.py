"""split_shipping_record_ledger_and_reconcile

Revision ID: a7d1f3d0bf91
Revises: d172eeea2723
Create Date: 2026-03-16 15:02:46.277145

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7d1f3d0bf91"
down_revision: Union[str, Sequence[str], None] = "d172eeea2723"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # 1) shipping_records：新增“物流台账”保留字段
    # ------------------------------------------------------------
    # 当前裁决：
    # - shipping_records 只保留“物流台账”主语义
    # - 目的地只保留省 / 市两列
    # - 对账相关事实迁移到独立表 shipping_record_reconciliations
    # ============================================================
    op.add_column(
        "shipping_records",
        sa.Column("dest_province", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("dest_city", sa.String(length=64), nullable=True),
    )

    # ============================================================
    # 2) 新建 shipping_record_reconciliations
    # ------------------------------------------------------------
    # 语义：
    # - 一条 shipping_record 最多对应一条当前对账结果
    # - carrier_bill_item_id 指向快递公司账单原始明细
    # - 对账差异与实际费用都落在这里，不污染物流台账主表
    # ============================================================
    op.create_table(
        "shipping_record_reconciliations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shipping_record_id", sa.BigInteger(), nullable=False),
        sa.Column("carrier_bill_item_id", sa.BigInteger(), nullable=True),
        sa.Column("billing_weight_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("freight_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("surcharge_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("cost_real", sa.Numeric(12, 2), nullable=True),
        sa.Column("weight_diff_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("cost_diff", sa.Numeric(12, 2), nullable=True),
        sa.Column("reconcile_status", sa.String(length=32), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconcile_note", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["carrier_bill_item_id"],
            ["carrier_bill_items.id"],
            name="fk_shipping_record_reconciliations_carrier_bill_item_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shipping_record_id"],
            ["shipping_records.id"],
            name="fk_shipping_record_reconciliations_shipping_record_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="shipping_record_reconciliations_pkey"),
        sa.UniqueConstraint(
            "shipping_record_id",
            name="uq_shipping_record_reconciliations_shipping_record_id",
        ),
    )

    op.create_index(
        "ix_shipping_record_reconciliations_status",
        "shipping_record_reconciliations",
        ["reconcile_status"],
        unique=False,
    )
    op.create_index(
        "ix_shipping_record_reconciliations_bill_item_id",
        "shipping_record_reconciliations",
        ["carrier_bill_item_id"],
        unique=False,
    )

    # ============================================================
    # 3) 删除 shipping_records 中“对账字段”
    # ------------------------------------------------------------
    # 裁决：
    # - 这些字段不再属于物流台账主表
    # - 全部迁出到 shipping_record_reconciliations
    # ============================================================
    op.drop_constraint(
        "fk_shipping_records_carrier_bill_item_id",
        "shipping_records",
        type_="foreignkey",
    )

    op.drop_index("ix_shipping_records_reconcile_status", table_name="shipping_records")

    op.drop_column("shipping_records", "billing_weight_kg")
    op.drop_column("shipping_records", "freight_amount")
    op.drop_column("shipping_records", "surcharge_amount")
    op.drop_column("shipping_records", "weight_diff_kg")
    op.drop_column("shipping_records", "cost_diff")
    op.drop_column("shipping_records", "reconcile_status")
    op.drop_column("shipping_records", "carrier_bill_item_id")
    op.drop_column("shipping_records", "reconciled_at")
    op.drop_column("shipping_records", "reconcile_note")


def downgrade() -> None:
    # ============================================================
    # 1) 恢复 shipping_records 上的对账字段
    # ============================================================
    op.add_column(
        "shipping_records",
        sa.Column("reconcile_note", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("carrier_bill_item_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("reconcile_status", sa.String(length=32), nullable=False),
    )
    op.add_column(
        "shipping_records",
        sa.Column("cost_diff", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("weight_diff_kg", sa.Numeric(10, 3), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("surcharge_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("freight_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "shipping_records",
        sa.Column("billing_weight_kg", sa.Numeric(10, 3), nullable=True),
    )

    op.create_index(
        "ix_shipping_records_reconcile_status",
        "shipping_records",
        ["reconcile_status"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_shipping_records_carrier_bill_item_id",
        "shipping_records",
        "carrier_bill_items",
        ["carrier_bill_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ============================================================
    # 2) 删除独立对账表
    # ============================================================
    op.drop_index(
        "ix_shipping_record_reconciliations_bill_item_id",
        table_name="shipping_record_reconciliations",
    )
    op.drop_index(
        "ix_shipping_record_reconciliations_status",
        table_name="shipping_record_reconciliations",
    )
    op.drop_table("shipping_record_reconciliations")

    # ============================================================
    # 3) 删除 shipping_records 新增的目的地字段
    # ============================================================
    op.drop_column("shipping_records", "dest_city")
    op.drop_column("shipping_records", "dest_province")
