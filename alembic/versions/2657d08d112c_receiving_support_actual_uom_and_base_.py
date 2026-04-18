"""receiving_support_actual_uom_and_base_qty_alignment

Revision ID: 2657d08d112c
Revises: d761227be296
Create Date: 2026-04-19 02:14:40.843985

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2657d08d112c"
down_revision: Union[str, Sequence[str], None] = "d761227be296"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    目标：
    - inbound_receipt_lines 继续表达“计划包装”
    - wms_inbound_operation_lines / inbound_event_lines 明确表达“实际包装”
    - 不新增双轨字段，直接重命名到终态语义
    """

    # ------------------------------------------------------------------
    # wms_inbound_operation_lines:
    #   item_uom_id            -> actual_item_uom_id
    #   uom_name_snapshot      -> actual_uom_name_snapshot
    #   ratio_to_base_snapshot -> actual_ratio_to_base_snapshot
    #   qty_inbound            -> actual_qty_input
    # ------------------------------------------------------------------
    op.alter_column(
        "wms_inbound_operation_lines",
        "item_uom_id",
        new_column_name="actual_item_uom_id",
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "uom_name_snapshot",
        new_column_name="actual_uom_name_snapshot",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "ratio_to_base_snapshot",
        new_column_name="actual_ratio_to_base_snapshot",
        existing_type=sa.Numeric(18, 6),
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "qty_inbound",
        new_column_name="actual_qty_input",
        existing_type=sa.Numeric(18, 6),
    )

    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT fk_wms_inbound_operation_lines_item_uom
        TO fk_wms_inbound_operation_lines_actual_item_uom
        """
    )
    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT ck_wms_inbound_operation_lines_ratio_positive
        TO ck_wms_inbound_operation_lines_actual_ratio_positive
        """
    )
    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT ck_wms_inbound_operation_lines_qty_inbound_positive
        TO ck_wms_inbound_operation_lines_actual_qty_input_positive
        """
    )
    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT ck_wms_inbound_operation_lines_qty_base_positive
        TO ck_wms_inbound_operation_lines_actual_qty_base_positive
        """
    )
    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT ck_wms_inbound_operation_lines_qty_base_consistent
        TO ck_wms_inbound_operation_lines_actual_qty_base_consistent
        """
    )

    # ------------------------------------------------------------------
    # inbound_event_lines:
    #   uom_id                 -> actual_uom_id
    #   ratio_to_base_snapshot -> actual_ratio_to_base_snapshot
    #   qty_input              -> actual_qty_input
    # ------------------------------------------------------------------
    op.alter_column(
        "inbound_event_lines",
        "uom_id",
        new_column_name="actual_uom_id",
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "inbound_event_lines",
        "ratio_to_base_snapshot",
        new_column_name="actual_ratio_to_base_snapshot",
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "inbound_event_lines",
        "qty_input",
        new_column_name="actual_qty_input",
        existing_type=sa.Integer(),
    )

    op.execute(
        """
        ALTER TABLE inbound_event_lines
        RENAME CONSTRAINT fk_inbound_event_lines_uom
        TO fk_inbound_event_lines_actual_uom
        """
    )
    op.execute(
        """
        ALTER TABLE inbound_event_lines
        RENAME CONSTRAINT ck_inbound_event_lines_ratio_positive
        TO ck_inbound_event_lines_actual_ratio_positive
        """
    )
    op.execute(
        """
        ALTER TABLE inbound_event_lines
        RENAME CONSTRAINT ck_inbound_event_lines_qty_input_positive
        TO ck_inbound_event_lines_actual_qty_input_positive
        """
    )
    op.execute(
        """
        ALTER TABLE inbound_event_lines
        RENAME CONSTRAINT ck_inbound_event_lines_qty_base_consistent
        TO ck_inbound_event_lines_actual_qty_base_consistent
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # ------------------------------------------------------------------
    # inbound_event_lines: reverse
    # ------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE inbound_event_lines
        RENAME CONSTRAINT fk_inbound_event_lines_actual_uom
        TO fk_inbound_event_lines_uom
        """
    )
    op.execute(
        """
        ALTER TABLE inbound_event_lines
        RENAME CONSTRAINT ck_inbound_event_lines_actual_ratio_positive
        TO ck_inbound_event_lines_ratio_positive
        """
    )
    op.execute(
        """
        ALTER TABLE inbound_event_lines
        RENAME CONSTRAINT ck_inbound_event_lines_actual_qty_input_positive
        TO ck_inbound_event_lines_qty_input_positive
        """
    )
    op.execute(
        """
        ALTER TABLE inbound_event_lines
        RENAME CONSTRAINT ck_inbound_event_lines_actual_qty_base_consistent
        TO ck_inbound_event_lines_qty_base_consistent
        """
    )

    op.alter_column(
        "inbound_event_lines",
        "actual_uom_id",
        new_column_name="uom_id",
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "inbound_event_lines",
        "actual_ratio_to_base_snapshot",
        new_column_name="ratio_to_base_snapshot",
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "inbound_event_lines",
        "actual_qty_input",
        new_column_name="qty_input",
        existing_type=sa.Integer(),
    )

    # ------------------------------------------------------------------
    # wms_inbound_operation_lines: reverse
    # ------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT fk_wms_inbound_operation_lines_actual_item_uom
        TO fk_wms_inbound_operation_lines_item_uom
        """
    )
    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT ck_wms_inbound_operation_lines_actual_ratio_positive
        TO ck_wms_inbound_operation_lines_ratio_positive
        """
    )
    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT ck_wms_inbound_operation_lines_actual_qty_input_positive
        TO ck_wms_inbound_operation_lines_qty_inbound_positive
        """
    )
    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT ck_wms_inbound_operation_lines_actual_qty_base_positive
        TO ck_wms_inbound_operation_lines_qty_base_positive
        """
    )
    op.execute(
        """
        ALTER TABLE wms_inbound_operation_lines
        RENAME CONSTRAINT ck_wms_inbound_operation_lines_actual_qty_base_consistent
        TO ck_wms_inbound_operation_lines_qty_base_consistent
        """
    )

    op.alter_column(
        "wms_inbound_operation_lines",
        "actual_item_uom_id",
        new_column_name="item_uom_id",
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "actual_uom_name_snapshot",
        new_column_name="uom_name_snapshot",
        existing_type=sa.String(length=64),
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "actual_ratio_to_base_snapshot",
        new_column_name="ratio_to_base_snapshot",
        existing_type=sa.Numeric(18, 6),
    )
    op.alter_column(
        "wms_inbound_operation_lines",
        "actual_qty_input",
        new_column_name="qty_inbound",
        existing_type=sa.Numeric(18, 6),
    )
