"""phase_m4_uom_contract_hard_cut

Revision ID: b544bf322a3d
Revises: a93d20ebd122
Create Date: 2026-03-01

M-4 硬切封板：
- PO & Receipt 切换到 uom_id + qty_input + qty_base 世界观
- 删除 case / units_per_case 残影
- 强制 ratio 语义
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b544bf322a3d"
down_revision: Union[str, Sequence[str], None] = "a93d20ebd122"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # =========================
    # 1️⃣ purchase_order_lines
    # =========================

    with op.batch_alter_table("purchase_order_lines") as bop:
        bop.add_column(sa.Column("purchase_uom_id_snapshot", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("purchase_ratio_to_base_snapshot", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("qty_ordered_input", sa.Integer(), nullable=True))

    # 回填 ratio + qty_input
    op.execute(
        """
        UPDATE purchase_order_lines
        SET
          purchase_ratio_to_base_snapshot = COALESCE(case_ratio_snapshot, 1),
          qty_ordered_input = COALESCE(qty_ordered_case_input, qty_ordered_base)
        """
    )

    # 回填 uom_id
    op.execute(
        """
        UPDATE purchase_order_lines p
        SET purchase_uom_id_snapshot = u.id
        FROM item_uoms u
        WHERE u.item_id = p.item_id
          AND u.ratio_to_base = p.purchase_ratio_to_base_snapshot
        """
    )

    # 强制非空 + FK
    with op.batch_alter_table("purchase_order_lines") as bop:
        bop.alter_column("purchase_uom_id_snapshot", nullable=False)
        bop.alter_column("purchase_ratio_to_base_snapshot", nullable=False)
        bop.alter_column("qty_ordered_input", nullable=False)

        bop.create_foreign_key(
            "fk_po_line_purchase_uom",
            "item_uoms",
            ["purchase_uom_id_snapshot"],
            ["id"],
        )

    # 删除旧字段 + 旧约束
    with op.batch_alter_table("purchase_order_lines") as bop:
        bop.drop_constraint("ck_po_line_case_input_valid", type_="check")
        bop.drop_column("case_ratio_snapshot")
        bop.drop_column("case_uom_snapshot")
        bop.drop_column("qty_ordered_case_input")

    # =========================
    # 2️⃣ inbound_receipt_lines
    # =========================

    with op.batch_alter_table("inbound_receipt_lines") as bop:
        bop.add_column(sa.Column("uom_id", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("qty_input", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("ratio_to_base_snapshot", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("qty_base", sa.Integer(), nullable=True))

    # 回填
    op.execute(
        """
        UPDATE inbound_receipt_lines
        SET
          qty_input = qty_received,
          ratio_to_base_snapshot = units_per_case,
          qty_base = qty_units
        """
    )

    # 回填 uom_id
    op.execute(
        """
        UPDATE inbound_receipt_lines r
        SET uom_id = u.id
        FROM item_uoms u
        WHERE u.item_id = r.item_id
          AND u.ratio_to_base = r.ratio_to_base_snapshot
        """
    )

    # 强制非空 + FK
    with op.batch_alter_table("inbound_receipt_lines") as bop:
        bop.alter_column("uom_id", nullable=False)
        bop.alter_column("qty_input", nullable=False)
        bop.alter_column("ratio_to_base_snapshot", nullable=False)
        bop.alter_column("qty_base", nullable=False)

        bop.create_foreign_key(
            "fk_receipt_line_uom",
            "item_uoms",
            ["uom_id"],
            ["id"],
        )

    # 新 check
    op.execute(
        """
        ALTER TABLE inbound_receipt_lines
        ADD CONSTRAINT ck_receipt_qty_base_consistent
        CHECK (qty_base = qty_input * ratio_to_base_snapshot)
        """
    )

    # 删除旧列 + 旧约束
    with op.batch_alter_table("inbound_receipt_lines") as bop:
        bop.drop_constraint("ck_inbound_receipt_lines_qty_units_consistent", type_="check")
        bop.drop_constraint("ck_inbound_receipt_lines_units_per_case_ge_1", type_="check")

        bop.drop_column("qty_received")
        bop.drop_column("units_per_case")
        bop.drop_column("qty_units")


def downgrade() -> None:
    raise Exception("Irreversible migration. Hard cut by design.")
