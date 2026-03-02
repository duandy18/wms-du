"""phase_m2 add warehouse_id and lot dims fk to inbound_receipt_lines

Revision ID: 9e7f145c0bfd
Revises: fe44b9b5353f
Create Date: 2026-02-28 15:24:21.045025

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9e7f145c0bfd"
down_revision: Union[str, Sequence[str], None] = "fe44b9b5353f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    inbound_receipt_lines 结构自解释（Phase M-2）：

    - add warehouse_id
    - backfill from inbound_receipts
    - NOT NULL
    - UNIQUE (receipt_id, line_no)
    - CHECK units_per_case >= 1
    - CHECK qty_units = qty_received * units_per_case
    - FK (lot_id, warehouse_id, item_id) -> lots(id, warehouse_id, item_id)
    """
    # 1) add warehouse_id (nullable first, for backfill)
    op.add_column(
        "inbound_receipt_lines",
        sa.Column("warehouse_id", sa.Integer(), nullable=True),
    )

    # 2) backfill warehouse_id from inbound_receipts
    op.execute(
        """
        UPDATE inbound_receipt_lines rl
        SET warehouse_id = r.warehouse_id
        FROM inbound_receipts r
        WHERE r.id = rl.receipt_id
          AND rl.warehouse_id IS NULL
        """
    )

    # 3) set NOT NULL
    op.alter_column(
        "inbound_receipt_lines",
        "warehouse_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # 4) unique (receipt_id, line_no)
    op.create_unique_constraint(
        "uq_inbound_receipt_lines_receipt_line",
        "inbound_receipt_lines",
        ["receipt_id", "line_no"],
    )

    # 5) CHECK: units_per_case >= 1
    op.create_check_constraint(
        "ck_inbound_receipt_lines_units_per_case_ge_1",
        "inbound_receipt_lines",
        "units_per_case >= 1",
    )

    # 6) CHECK: qty_units = qty_received * units_per_case
    op.create_check_constraint(
        "ck_inbound_receipt_lines_qty_units_consistent",
        "inbound_receipt_lines",
        "qty_units = qty_received * units_per_case",
    )

    # 7) composite FK to lots
    op.create_foreign_key(
        "fk_inbound_receipt_lines_lot_dims",
        "inbound_receipt_lines",
        "lots",
        ["lot_id", "warehouse_id", "item_id"],
        ["id", "warehouse_id", "item_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_inbound_receipt_lines_lot_dims",
        "inbound_receipt_lines",
        type_="foreignkey",
    )

    op.drop_constraint(
        "ck_inbound_receipt_lines_qty_units_consistent",
        "inbound_receipt_lines",
        type_="check",
    )

    op.drop_constraint(
        "ck_inbound_receipt_lines_units_per_case_ge_1",
        "inbound_receipt_lines",
        type_="check",
    )

    op.drop_constraint(
        "uq_inbound_receipt_lines_receipt_line",
        "inbound_receipt_lines",
        type_="unique",
    )

    op.drop_column("inbound_receipt_lines", "warehouse_id")
