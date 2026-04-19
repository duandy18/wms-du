"""receiving_receipt_qty_integer_cutover

Revision ID: fd46309adb9d
Revises: 2657d08d112c
Create Date: 2026-04-19 16:37:10.776009

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fd46309adb9d"
down_revision: Union[str, Sequence[str], None] = "2657d08d112c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_no_fractional_receipt_rows() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM inbound_receipt_lines
            WHERE planned_qty <> trunc(planned_qty)
               OR ratio_to_base_snapshot <> trunc(ratio_to_base_snapshot)
               OR (planned_qty * ratio_to_base_snapshot) <> trunc(planned_qty * ratio_to_base_snapshot)
          ) THEN
            RAISE EXCEPTION
              'inbound_receipt_lines contains non-integer quantity data; abort integer cutover';
          END IF;
        END
        $$;
        """
    )


def _assert_no_fractional_operation_rows() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM wms_inbound_operation_lines
            WHERE actual_qty_input <> trunc(actual_qty_input)
               OR actual_ratio_to_base_snapshot <> trunc(actual_ratio_to_base_snapshot)
               OR qty_base <> trunc(qty_base)
               OR qty_base <> (actual_qty_input * actual_ratio_to_base_snapshot)
          ) THEN
            RAISE EXCEPTION
              'wms_inbound_operation_lines contains non-integer or inconsistent quantity data; abort integer cutover';
          END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    """Upgrade schema."""
    _assert_no_fractional_receipt_rows()
    _assert_no_fractional_operation_rows()

    op.drop_constraint(
        "ck_inbound_receipt_lines_planned_qty_positive",
        "inbound_receipt_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_inbound_receipt_lines_ratio_positive",
        "inbound_receipt_lines",
        type_="check",
    )

    op.drop_constraint(
        "ck_wms_inbound_operation_lines_actual_ratio_positive",
        "wms_inbound_operation_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_input_positive",
        "wms_inbound_operation_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_base_positive",
        "wms_inbound_operation_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_base_consistent",
        "wms_inbound_operation_lines",
        type_="check",
    )

    op.alter_column(
        "inbound_receipt_lines",
        "planned_qty",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Integer(),
        postgresql_using="planned_qty::integer",
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipt_lines",
        "ratio_to_base_snapshot",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Integer(),
        postgresql_using="ratio_to_base_snapshot::integer",
        existing_nullable=False,
    )

    op.alter_column(
        "wms_inbound_operation_lines",
        "actual_ratio_to_base_snapshot",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Integer(),
        postgresql_using="actual_ratio_to_base_snapshot::integer",
        existing_nullable=False,
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "actual_qty_input",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Integer(),
        postgresql_using="actual_qty_input::integer",
        existing_nullable=False,
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "qty_base",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Integer(),
        postgresql_using="qty_base::integer",
        existing_nullable=False,
    )

    op.create_check_constraint(
        "ck_inbound_receipt_lines_planned_qty_positive",
        "inbound_receipt_lines",
        "planned_qty > 0",
    )
    op.create_check_constraint(
        "ck_inbound_receipt_lines_ratio_positive",
        "inbound_receipt_lines",
        "ratio_to_base_snapshot > 0",
    )

    op.create_check_constraint(
        "ck_wms_inbound_operation_lines_actual_ratio_positive",
        "wms_inbound_operation_lines",
        "actual_ratio_to_base_snapshot > 0",
    )
    op.create_check_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_input_positive",
        "wms_inbound_operation_lines",
        "actual_qty_input > 0",
    )
    op.create_check_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_base_positive",
        "wms_inbound_operation_lines",
        "qty_base > 0",
    )
    op.create_check_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_base_consistent",
        "wms_inbound_operation_lines",
        "qty_base = (actual_qty_input * actual_ratio_to_base_snapshot)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_inbound_receipt_lines_planned_qty_positive",
        "inbound_receipt_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_inbound_receipt_lines_ratio_positive",
        "inbound_receipt_lines",
        type_="check",
    )

    op.drop_constraint(
        "ck_wms_inbound_operation_lines_actual_ratio_positive",
        "wms_inbound_operation_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_input_positive",
        "wms_inbound_operation_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_base_positive",
        "wms_inbound_operation_lines",
        type_="check",
    )
    op.drop_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_base_consistent",
        "wms_inbound_operation_lines",
        type_="check",
    )

    op.alter_column(
        "inbound_receipt_lines",
        "planned_qty",
        existing_type=sa.Integer(),
        type_=sa.Numeric(18, 6),
        postgresql_using="planned_qty::numeric(18,6)",
        existing_nullable=False,
    )
    op.alter_column(
        "inbound_receipt_lines",
        "ratio_to_base_snapshot",
        existing_type=sa.Integer(),
        type_=sa.Numeric(18, 6),
        postgresql_using="ratio_to_base_snapshot::numeric(18,6)",
        existing_nullable=False,
    )

    op.alter_column(
        "wms_inbound_operation_lines",
        "actual_ratio_to_base_snapshot",
        existing_type=sa.Integer(),
        type_=sa.Numeric(18, 6),
        postgresql_using="actual_ratio_to_base_snapshot::numeric(18,6)",
        existing_nullable=False,
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "actual_qty_input",
        existing_type=sa.Integer(),
        type_=sa.Numeric(18, 6),
        postgresql_using="actual_qty_input::numeric(18,6)",
        existing_nullable=False,
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "qty_base",
        existing_type=sa.Integer(),
        type_=sa.Numeric(18, 6),
        postgresql_using="qty_base::numeric(18,6)",
        existing_nullable=False,
    )

    op.create_check_constraint(
        "ck_inbound_receipt_lines_planned_qty_positive",
        "inbound_receipt_lines",
        "planned_qty > 0",
    )
    op.create_check_constraint(
        "ck_inbound_receipt_lines_ratio_positive",
        "inbound_receipt_lines",
        "ratio_to_base_snapshot > 0",
    )

    op.create_check_constraint(
        "ck_wms_inbound_operation_lines_actual_ratio_positive",
        "wms_inbound_operation_lines",
        "actual_ratio_to_base_snapshot > 0",
    )
    op.create_check_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_input_positive",
        "wms_inbound_operation_lines",
        "actual_qty_input > 0",
    )
    op.create_check_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_base_positive",
        "wms_inbound_operation_lines",
        "qty_base > 0",
    )
    op.create_check_constraint(
        "ck_wms_inbound_operation_lines_actual_qty_base_consistent",
        "wms_inbound_operation_lines",
        "qty_base = (actual_qty_input * actual_ratio_to_base_snapshot)",
    )
