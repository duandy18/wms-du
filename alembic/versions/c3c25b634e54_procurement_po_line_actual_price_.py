"""procurement po line actual price contract

Revision ID: c3c25b634e54
Revises: b5a434c26633
Create Date: 2026-04-25 22:30:42.154449

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3c25b634e54"
down_revision: Union[str, Sequence[str], None] = "b5a434c26633"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 终态口径：
    # supply_price = 已折扣后的实际基础单位采购价
    # 采购总价 = supply_price * qty_ordered_base
    op.execute(
        """
        UPDATE purchase_order_line_completion
           SET planned_line_amount = (
             COALESCE(supply_price_snapshot, 0::numeric(12, 2))
             * COALESCE(qty_ordered_base, 0)
           )::numeric(14, 2)
        """
    )

    op.execute(
        """
        UPDATE purchase_orders po
           SET total_amount = COALESCE(src.total_amount, 0::numeric(14, 2))
          FROM (
            SELECT
              pol.po_id,
              SUM(
                COALESCE(pol.supply_price, 0::numeric(12, 2))
                * COALESCE(pol.qty_ordered_base, 0)
              )::numeric(14, 2) AS total_amount
            FROM purchase_order_lines pol
            GROUP BY pol.po_id
          ) src
         WHERE src.po_id = po.id
        """
    )

    op.execute(
        """
        ALTER TABLE purchase_order_line_completion
        DROP CONSTRAINT IF EXISTS ck_polc_discount_amount_snapshot_nonneg
        """
    )

    op.execute(
        """
        ALTER TABLE purchase_order_line_completion
        DROP COLUMN IF EXISTS discount_amount_snapshot
        """
    )

    op.execute(
        """
        ALTER TABLE purchase_order_lines
        DROP CONSTRAINT IF EXISTS ck_po_lines_discount_amount_nonneg
        """
    )

    op.execute(
        """
        ALTER TABLE purchase_order_lines
        DROP COLUMN IF EXISTS discount_note
        """
    )

    op.execute(
        """
        ALTER TABLE purchase_order_lines
        DROP COLUMN IF EXISTS discount_amount
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.execute(
        """
        ALTER TABLE purchase_order_lines
        ADD COLUMN IF NOT EXISTS discount_amount numeric(14, 2) NOT NULL DEFAULT 0
        """
    )

    op.execute(
        """
        COMMENT ON COLUMN purchase_order_lines.discount_amount
        IS '整行减免金额（>=0）'
        """
    )

    op.execute(
        """
        ALTER TABLE purchase_order_lines
        ADD COLUMN IF NOT EXISTS discount_note text
        """
    )

    op.execute(
        """
        COMMENT ON COLUMN purchase_order_lines.discount_note
        IS '折扣说明（可选）'
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_po_lines_discount_amount_nonneg'
               AND conrelid = 'purchase_order_lines'::regclass
          ) THEN
            ALTER TABLE purchase_order_lines
            ADD CONSTRAINT ck_po_lines_discount_amount_nonneg
            CHECK (discount_amount >= 0);
          END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        ALTER TABLE purchase_order_line_completion
        ADD COLUMN IF NOT EXISTS discount_amount_snapshot numeric(14, 2) NOT NULL DEFAULT 0
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_polc_discount_amount_snapshot_nonneg'
               AND conrelid = 'purchase_order_line_completion'::regclass
          ) THEN
            ALTER TABLE purchase_order_line_completion
            ADD CONSTRAINT ck_polc_discount_amount_snapshot_nonneg
            CHECK (discount_amount_snapshot >= 0);
          END IF;
        END
        $$;
        """
    )
