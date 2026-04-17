"""fix inbound receipt schema drift

Revision ID: 0e6706881685
Revises: bb5d85b12ff8
Create Date: 2026-04-17 17:07:54.861886

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0e6706881685"
down_revision: Union[str, Sequence[str], None] = "bb5d85b12ff8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) inbound_receipts.receipt_no: varchar(128) -> varchar(64)
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM inbound_receipts
            WHERE length(receipt_no) > 64
          ) THEN
            RAISE EXCEPTION 'inbound_receipts.receipt_no has values longer than 64';
          END IF;
        END $$;
        """
    )

    op.alter_column(
        "inbound_receipts",
        "receipt_no",
        existing_type=sa.String(length=128),
        type_=sa.String(length=64),
        existing_nullable=False,
    )

    # 2) inbound_receipt_lines.item_uom_id FK: rebuild with ON DELETE RESTRICT
    op.drop_constraint(
        "fk_inbound_receipt_lines_item_uom",
        "inbound_receipt_lines",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_lines_item_uom",
        "inbound_receipt_lines",
        "item_uoms",
        ["item_uom_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_inbound_receipt_lines_item_uom",
        "inbound_receipt_lines",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_lines_item_uom",
        "inbound_receipt_lines",
        "item_uoms",
        ["item_uom_id"],
        ["id"],
    )

    op.alter_column(
        "inbound_receipts",
        "receipt_no",
        existing_type=sa.String(length=64),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
