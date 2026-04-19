"""wms outbound event lines

Revision ID: 17f99d5d97cf
Revises: fd46309adb9d
Create Date: 2026-04-19 19:31:53.294716

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "17f99d5d97cf"
down_revision: Union[str, Sequence[str], None] = "fd46309adb9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 扩 wms_events.source_type：补 ORDER
    op.execute(
        """
        ALTER TABLE wms_events
        DROP CONSTRAINT IF EXISTS ck_wms_events_source_type
        """
    )
    op.execute(
        """
        ALTER TABLE wms_events
        ADD CONSTRAINT ck_wms_events_source_type
        CHECK (
          source_type IN (
            'PURCHASE_ORDER',
            'MANUAL',
            'RETURN',
            'TRANSFER_IN',
            'ADJUST_IN',
            'ORDER'
          )
        )
        """
    )

    # 2) 出库事件行
    op.create_table(
        "outbound_event_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("ref_line", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("qty_outbound", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("lot_code_snapshot", sa.String(length=64), nullable=True),
        sa.Column("order_line_id", sa.BigInteger(), nullable=True),
        sa.Column("manual_doc_line_id", sa.BigInteger(), nullable=True),
        sa.Column("item_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("item_spec_snapshot", sa.String(length=255), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["wms_events.id"],
            name="fk_outbound_event_lines_event",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_line_id"],
            ["order_lines.id"],
            name="fk_outbound_event_lines_order_line",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "qty_outbound > 0",
            name="ck_outbound_event_lines_qty_positive",
        ),
        sa.UniqueConstraint(
            "event_id",
            "ref_line",
            name="uq_outbound_event_lines_event_ref_line",
        ),
        sa.CheckConstraint(
            """
            (order_line_id IS NOT NULL AND manual_doc_line_id IS NULL)
            OR
            (order_line_id IS NULL AND manual_doc_line_id IS NOT NULL)
            """,
            name="ck_outbound_event_lines_source_oneof",
        ),
    )

    op.create_index(
        "ix_outbound_event_lines_event_id",
        "outbound_event_lines",
        ["event_id"],
    )
    op.create_index(
        "ix_outbound_event_lines_item_id",
        "outbound_event_lines",
        ["item_id"],
    )
    op.create_index(
        "ix_outbound_event_lines_order_line_id",
        "outbound_event_lines",
        ["order_line_id"],
    )
    op.create_index(
        "ix_outbound_event_lines_manual_doc_line_id",
        "outbound_event_lines",
        ["manual_doc_line_id"],
    )
    op.create_index(
        "ix_outbound_event_lines_lot_id",
        "outbound_event_lines",
        ["lot_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbound_event_lines_lot_id", table_name="outbound_event_lines")
    op.drop_index("ix_outbound_event_lines_manual_doc_line_id", table_name="outbound_event_lines")
    op.drop_index("ix_outbound_event_lines_order_line_id", table_name="outbound_event_lines")
    op.drop_index("ix_outbound_event_lines_item_id", table_name="outbound_event_lines")
    op.drop_index("ix_outbound_event_lines_event_id", table_name="outbound_event_lines")
    op.drop_table("outbound_event_lines")

    op.execute(
        """
        ALTER TABLE wms_events
        DROP CONSTRAINT IF EXISTS ck_wms_events_source_type
        """
    )
    op.execute(
        """
        ALTER TABLE wms_events
        ADD CONSTRAINT ck_wms_events_source_type
        CHECK (
          source_type IN (
            'PURCHASE_ORDER',
            'MANUAL',
            'RETURN',
            'TRANSFER_IN',
            'ADJUST_IN'
          )
        )
        """
    )
