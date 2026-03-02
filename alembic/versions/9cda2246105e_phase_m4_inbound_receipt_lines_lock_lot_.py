"""phase m4: inbound_receipt_lines lock lot dims and lot_id not null

Revision ID: 9cda2246105e
Revises: 1c11efa494f2
Create Date: 2026-03-01 12:55:59.013031

- enforce lot_id NOT NULL (lot-only world)
- enforce composite FK (lot_id, warehouse_id, item_id) -> lots(id, warehouse_id, item_id)
- ensure warehouse_id FK -> warehouses(id) (conditional)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9cda2246105e"
down_revision: Union[str, Sequence[str], None] = "1c11efa494f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ------------------------------------------------------------------
    # 1) lot_id must be NOT NULL
    # ------------------------------------------------------------------
    op.alter_column(
        "inbound_receipt_lines",
        "lot_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # 2) composite FK to lots dims
    #    (lot_id, warehouse_id, item_id) -> lots(id, warehouse_id, item_id)
    # ------------------------------------------------------------------
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_inbound_receipt_lines_lot_dims'
  ) THEN
    ALTER TABLE public.inbound_receipt_lines
      ADD CONSTRAINT fk_inbound_receipt_lines_lot_dims
      FOREIGN KEY (lot_id, warehouse_id, item_id)
      REFERENCES public.lots (id, warehouse_id, item_id)
      ON DELETE RESTRICT;
  END IF;
END $$;
"""
    )

    # ------------------------------------------------------------------
    # 3) warehouse_id FK -> warehouses(id) (if not already present)
    # ------------------------------------------------------------------
    op.execute(
        """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_inbound_receipt_lines_warehouse'
  ) THEN
    ALTER TABLE public.inbound_receipt_lines
      ADD CONSTRAINT fk_inbound_receipt_lines_warehouse
      FOREIGN KEY (warehouse_id)
      REFERENCES public.warehouses (id)
      ON DELETE RESTRICT;
  END IF;
END $$;
"""
    )


def downgrade() -> None:
    """Downgrade schema."""

    # Drop warehouse FK if exists
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_inbound_receipt_lines_warehouse'
  ) THEN
    ALTER TABLE public.inbound_receipt_lines
      DROP CONSTRAINT fk_inbound_receipt_lines_warehouse;
  END IF;
END $$;
"""
    )

    # Drop lot dims FK if exists
    op.execute(
        """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_inbound_receipt_lines_lot_dims'
  ) THEN
    ALTER TABLE public.inbound_receipt_lines
      DROP CONSTRAINT fk_inbound_receipt_lines_lot_dims;
  END IF;
END $$;
"""
    )

    # Make lot_id nullable again
    op.alter_column(
        "inbound_receipt_lines",
        "lot_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
