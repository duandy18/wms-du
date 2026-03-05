"""add inbound_receipt_draft_line_scan_events

Revision ID: 6ee179e0cf29
Revises: 0f94288a837b
Create Date: 2026-02-17 19:49:40.751698

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "6ee179e0cf29"
down_revision: Union[str, Sequence[str], None] = "0f94288a837b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    目标：扫码证据挂在“草稿收货单行”上（draft_line），不污染事实凭证层。
    """
    op.create_table(
        "inbound_receipt_draft_line_scan_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.BigInteger(), nullable=False),
        sa.Column("draft_line_id", sa.BigInteger(), nullable=False),
        sa.Column("po_id", sa.Integer(), nullable=False),
        sa.Column("po_line_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("raw_barcode", sa.Text(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column(
            "parsed",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_foreign_key(
        "fk_inb_rcpt_draft_scan_draft",
        "inbound_receipt_draft_line_scan_events",
        "inbound_receipt_drafts",
        ["draft_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_inb_rcpt_draft_scan_draft_line",
        "inbound_receipt_draft_line_scan_events",
        "inbound_receipt_draft_lines",
        ["draft_line_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_inb_rcpt_draft_scan_po",
        "inbound_receipt_draft_line_scan_events",
        "purchase_orders",
        ["po_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inb_rcpt_draft_scan_po_line",
        "inbound_receipt_draft_line_scan_events",
        "purchase_order_lines",
        ["po_line_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inb_rcpt_draft_scan_item",
        "inbound_receipt_draft_line_scan_events",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 索引：行内回显“最近扫码条码代号”
    op.create_index(
        "ix_inb_rcpt_draft_scan_draft_line_created_at",
        "inbound_receipt_draft_line_scan_events",
        ["draft_line_id", "created_at"],
    )
    op.create_index(
        "ix_inb_rcpt_draft_scan_draft_created_at",
        "inbound_receipt_draft_line_scan_events",
        ["draft_id", "created_at"],
    )
    op.create_index(
        "ix_inb_rcpt_draft_scan_po_created_at",
        "inbound_receipt_draft_line_scan_events",
        ["po_id", "created_at"],
    )
    op.create_index(
        "ix_inb_rcpt_draft_scan_item_created_at",
        "inbound_receipt_draft_line_scan_events",
        ["item_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_inb_rcpt_draft_scan_item_created_at", table_name="inbound_receipt_draft_line_scan_events")
    op.drop_index("ix_inb_rcpt_draft_scan_po_created_at", table_name="inbound_receipt_draft_line_scan_events")
    op.drop_index("ix_inb_rcpt_draft_scan_draft_created_at", table_name="inbound_receipt_draft_line_scan_events")
    op.drop_index("ix_inb_rcpt_draft_scan_draft_line_created_at", table_name="inbound_receipt_draft_line_scan_events")

    op.drop_constraint("fk_inb_rcpt_draft_scan_item", "inbound_receipt_draft_line_scan_events", type_="foreignkey")
    op.drop_constraint("fk_inb_rcpt_draft_scan_po_line", "inbound_receipt_draft_line_scan_events", type_="foreignkey")
    op.drop_constraint("fk_inb_rcpt_draft_scan_po", "inbound_receipt_draft_line_scan_events", type_="foreignkey")
    op.drop_constraint("fk_inb_rcpt_draft_scan_draft_line", "inbound_receipt_draft_line_scan_events", type_="foreignkey")
    op.drop_constraint("fk_inb_rcpt_draft_scan_draft", "inbound_receipt_draft_line_scan_events", type_="foreignkey")

    op.drop_table("inbound_receipt_draft_line_scan_events")
