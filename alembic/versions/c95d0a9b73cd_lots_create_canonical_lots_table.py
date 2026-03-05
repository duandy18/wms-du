"""lots: create canonical lots table

Revision ID: c95d0a9b73cd
Revises: cf7f038c35ff
Create Date: 2026-02-24 13:21:08.489211
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c95d0a9b73cd"
down_revision: Union[str, Sequence[str], None] = "cf7f038c35ff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase 2 - Step 1

    新建 canonical lots 表。
    仅创建结构，不回填历史数据，不改写现有逻辑。
    """

    op.create_table(
        "lots",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("lot_code_source", sa.String(length=16), nullable=False),
        sa.Column("lot_code", sa.String(length=64), nullable=True),
        sa.Column("source_receipt_id", sa.Integer(), nullable=True),
        sa.Column("source_line_no", sa.Integer(), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("expiry_source", sa.String(length=16), nullable=True),
        sa.Column("shelf_life_days_applied", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ---------------------------
    # Foreign Keys
    # ---------------------------

    op.create_foreign_key(
        "fk_lots_warehouse",
        "lots",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_lots_item",
        "lots",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_lots_source_receipt",
        "lots",
        "inbound_receipts",
        ["source_receipt_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ---------------------------
    # CHECK Constraints
    # ---------------------------

    # lot_code_source 枚举
    op.create_check_constraint(
        "ck_lots_lot_code_source",
        "lots",
        "lot_code_source IN ('SUPPLIER', 'INTERNAL')",
    )

    # SUPPLIER: 必须有 lot_code，且不能绑定来源
    op.create_check_constraint(
        "ck_lots_supplier_requires_lot_code_and_no_source",
        "lots",
        "("
        "lot_code_source <> 'SUPPLIER' OR "
        "(lot_code IS NOT NULL AND source_receipt_id IS NULL AND source_line_no IS NULL)"
        ")",
    )

    # INTERNAL: 必须绑定 receipt_id + line_no
    op.create_check_constraint(
        "ck_lots_internal_requires_source",
        "lots",
        "("
        "lot_code_source <> 'INTERNAL' OR "
        "(source_receipt_id IS NOT NULL AND source_line_no IS NOT NULL)"
        ")",
    )

    # expiry_source 枚举（可为空）
    op.create_check_constraint(
        "ck_lots_expiry_source_enum",
        "lots",
        "("
        "expiry_source IS NULL OR expiry_source IN ('EXPLICIT', 'DERIVED')"
        ")",
    )

    # ---------------------------
    # Indexes
    # ---------------------------

    op.create_index(
        "ix_lots_wh_item",
        "lots",
        ["warehouse_id", "item_id"],
        unique=False,
    )

    op.create_index(
        "ix_lots_item",
        "lots",
        ["item_id"],
        unique=False,
    )

    op.create_index(
        "ix_lots_wh",
        "lots",
        ["warehouse_id"],
        unique=False,
    )

    # SUPPLIER unique
    op.create_index(
        "uq_lots_supplier_wh_item_lot_code",
        "lots",
        ["warehouse_id", "item_id", "lot_code_source", "lot_code"],
        unique=True,
        postgresql_where=sa.text("lot_code_source = 'SUPPLIER'"),
    )

    # INTERNAL unique
    op.create_index(
        "uq_lots_internal_wh_item_source",
        "lots",
        [
            "warehouse_id",
            "item_id",
            "lot_code_source",
            "source_receipt_id",
            "source_line_no",
        ],
        unique=True,
        postgresql_where=sa.text("lot_code_source = 'INTERNAL'"),
    )


def downgrade() -> None:
    """
    仅删除 lots 表。
    """

    op.drop_index("uq_lots_internal_wh_item_source", table_name="lots")
    op.drop_index("uq_lots_supplier_wh_item_lot_code", table_name="lots")
    op.drop_index("ix_lots_wh_item", table_name="lots")
    op.drop_index("ix_lots_item", table_name="lots")
    op.drop_index("ix_lots_wh", table_name="lots")

    op.drop_table("lots")
