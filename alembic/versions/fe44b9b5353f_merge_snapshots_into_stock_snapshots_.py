"""merge snapshots into stock_snapshots and drop snapshots

Revision ID: fe44b9b5353f
Revises: fe9a13506faf
Create Date: 2026-02-28 14:28:56.504772

Route B (one-step hard merge):

- Enforce no-prealloc invariant on stock_snapshots:
    qty_allocated = 0 AND qty_available = qty
- Fail if overlapping keys disagree on qty.
- Insert missing rows from snapshots into stock_snapshots.
- Drop legacy table snapshots.

Irreversible migration.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fe44b9b5353f"
down_revision: Union[str, Sequence[str], None] = "fe9a13506faf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------
    # 0) Fail-fast checks
    # ------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
          bad_cnt int;
        BEGIN
          -- A) stock_snapshots must satisfy no-prealloc invariants
          SELECT COUNT(*) INTO bad_cnt
          FROM public.stock_snapshots
          WHERE qty_allocated <> 0 OR qty_available <> qty;

          IF bad_cnt > 0 THEN
            RAISE EXCEPTION
              'stock_snapshots violates no-prealloc invariants: % rows (qty_allocated must be 0 and qty_available must equal qty)',
              bad_cnt;
          END IF;

          -- B) overlapping keys must have identical qty
          SELECT COUNT(*) INTO bad_cnt
          FROM public.snapshots s
          JOIN public.stock_snapshots ss
            ON ss.snapshot_date = s.snapshot_date
           AND ss.warehouse_id = s.warehouse_id
           AND ss.item_id = s.item_id
           AND ss.lot_id = s.lot_id
          WHERE ss.qty <> (s.qty_on_hand::numeric(18,4));

          IF bad_cnt > 0 THEN
            RAISE EXCEPTION
              'snapshots vs stock_snapshots qty mismatch on % overlapping rows; resolve before merge',
              bad_cnt;
          END IF;
        END $$;
        """
    )

    # ------------------------------------------------------------
    # 1) Insert missing rows from snapshots -> stock_snapshots
    # ------------------------------------------------------------
    op.execute(
        """
        INSERT INTO public.stock_snapshots(
          snapshot_date,
          warehouse_id,
          item_id,
          lot_id,
          qty,
          qty_allocated,
          qty_available
        )
        SELECT
          s.snapshot_date,
          s.warehouse_id,
          s.item_id,
          s.lot_id,
          (s.qty_on_hand::numeric(18,4)) AS qty,
          0::numeric(18,4) AS qty_allocated,
          (s.qty_on_hand::numeric(18,4)) AS qty_available
        FROM public.snapshots s
        WHERE NOT EXISTS (
          SELECT 1
          FROM public.stock_snapshots ss
          WHERE ss.snapshot_date = s.snapshot_date
            AND ss.warehouse_id = s.warehouse_id
            AND ss.item_id = s.item_id
            AND ss.lot_id = s.lot_id
        );
        """
    )

    # ------------------------------------------------------------
    # 2) Drop legacy table snapshots
    # ------------------------------------------------------------
    op.drop_table("snapshots")


def downgrade() -> None:
    raise NotImplementedError(
        "One-way migration: snapshots table dropped after merge into stock_snapshots."
    )
