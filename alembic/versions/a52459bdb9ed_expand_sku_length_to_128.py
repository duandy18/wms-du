"""expand_sku_length_to_128

Revision ID: a52459bdb9ed
Revises: '0bf1c4ffb51a'
Create Date: 2026-04-29

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a52459bdb9ed"
down_revision: Union[str, Sequence[str], None] = '0bf1c4ffb51a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand SKU-like business code fields to 128."""

    op.alter_column("items", "sku", existing_type=sa.String(length=64), type_=sa.String(length=128), existing_nullable=False)
    op.alter_column("fskus", "code", existing_type=sa.String(length=64), type_=sa.String(length=128), existing_nullable=False)

    op.alter_column("purchase_order_lines", "item_sku", existing_type=sa.String(length=64), type_=sa.String(length=128), existing_nullable=True)
    op.alter_column("purchase_order_line_completion", "item_sku", existing_type=sa.String(length=64), type_=sa.String(length=128), existing_nullable=True)
    op.alter_column("finance_purchase_price_ledger_lines", "item_sku", existing_type=sa.String(length=64), type_=sa.String(length=128), existing_nullable=True)

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'outbound_event_lines'
              AND column_name = 'item_sku_snapshot'
          ) THEN
            ALTER TABLE outbound_event_lines
            ALTER COLUMN item_sku_snapshot TYPE varchar(128);
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Shrink SKU-like business code fields back to 64."""

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM items WHERE length(sku) > 64
          ) THEN
            RAISE EXCEPTION 'cannot downgrade: items.sku contains values longer than 64';
          END IF;

          IF EXISTS (
            SELECT 1 FROM fskus WHERE length(code) > 64
          ) THEN
            RAISE EXCEPTION 'cannot downgrade: fskus.code contains values longer than 64';
          END IF;

          IF EXISTS (
            SELECT 1 FROM purchase_order_lines WHERE length(item_sku) > 64
          ) THEN
            RAISE EXCEPTION 'cannot downgrade: purchase_order_lines.item_sku contains values longer than 64';
          END IF;

          IF EXISTS (
            SELECT 1 FROM purchase_order_line_completion WHERE length(item_sku) > 64
          ) THEN
            RAISE EXCEPTION 'cannot downgrade: purchase_order_line_completion.item_sku contains values longer than 64';
          END IF;

          IF EXISTS (
            SELECT 1 FROM finance_purchase_price_ledger_lines WHERE length(item_sku) > 64
          ) THEN
            RAISE EXCEPTION 'cannot downgrade: finance_purchase_price_ledger_lines.item_sku contains values longer than 64';
          END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'outbound_event_lines'
              AND column_name = 'item_sku_snapshot'
          ) THEN
            ALTER TABLE outbound_event_lines
            ALTER COLUMN item_sku_snapshot TYPE varchar(64);
          END IF;
        END $$;
        """
    )

    op.alter_column("finance_purchase_price_ledger_lines", "item_sku", existing_type=sa.String(length=128), type_=sa.String(length=64), existing_nullable=True)
    op.alter_column("purchase_order_line_completion", "item_sku", existing_type=sa.String(length=128), type_=sa.String(length=64), existing_nullable=True)
    op.alter_column("purchase_order_lines", "item_sku", existing_type=sa.String(length=128), type_=sa.String(length=64), existing_nullable=True)

    op.alter_column("fskus", "code", existing_type=sa.String(length=128), type_=sa.String(length=64), existing_nullable=False)
    op.alter_column("items", "sku", existing_type=sa.String(length=128), type_=sa.String(length=64), existing_nullable=False)
