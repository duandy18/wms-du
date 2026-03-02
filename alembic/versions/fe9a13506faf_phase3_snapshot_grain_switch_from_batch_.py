"""phase3 snapshot grain switch from batch to lot (one-step)

Revision ID: fe9a13506faf
Revises: e0dcd4408c55
Create Date: 2026-02-28 14:10:55.051433

Hard switch snapshot grain from (snapshot_date, wh, item, batch_code_key|batch_code)
to (snapshot_date, wh, item, lot_id) without renaming tables.

Tables:
- stock_snapshots (v2, batch_code nullable + generated batch_code_key)
- snapshots (v1, batch_code NOT NULL)

Strategy:
1) Add lot_id nullable columns.
2) Ensure required lots exist (SUPPLIER lot_code=batch_code; INTERNAL 'INTERNAL-SNAPSHOT' for NULL batch slot).
3) Backfill lot_id via join lots.
4) Fail-fast if any NULL remains.
5) Drop old batch grain constraints/indexes/columns.
6) Add composite FK dims + new unique grain + indexes.

NOTE:
- lots has a partial UNIQUE INDEX uq_lots_wh_item_lot_code (WHERE lot_code IS NOT NULL),
  so we must use ON CONFLICT (warehouse_id,item_id,lot_code) WHERE lot_code IS NOT NULL.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fe9a13506faf"
down_revision: Union[str, Sequence[str], None] = "e0dcd4408c55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------
    # 0) Add lot_id columns (nullable for backfill)
    # ------------------------------------------------------------
    with op.batch_alter_table("stock_snapshots") as bop:
        bop.add_column(sa.Column("lot_id", sa.Integer(), nullable=True))

    with op.batch_alter_table("snapshots") as bop:
        bop.add_column(sa.Column("lot_id", sa.Integer(), nullable=True))

    # ------------------------------------------------------------
    # 1) Ensure lots exist for snapshot slots (idempotent)
    #    - batch_code NOT NULL => SUPPLIER lot with lot_code=batch_code
    #    - stock_snapshots batch_code NULL => INTERNAL lot with stable code 'INTERNAL-SNAPSHOT'
    #
    # lots requires policy snapshots NOT NULL -> source from items
    # ------------------------------------------------------------

    # 1.1) Create SUPPLIER lots for all (wh,item,batch_code) from BOTH tables where batch_code IS NOT NULL
    op.execute(
        """
        WITH keys AS (
          SELECT DISTINCT warehouse_id, item_id, batch_code::varchar(64) AS lot_code
          FROM public.stock_snapshots
          WHERE batch_code IS NOT NULL
          UNION
          SELECT DISTINCT warehouse_id, item_id, batch_code::varchar(64) AS lot_code
          FROM public.snapshots
          WHERE batch_code IS NOT NULL
        )
        INSERT INTO public.lots(
          warehouse_id, item_id, lot_code_source, lot_code,
          source_receipt_id, source_line_no,
          created_at,
          item_has_shelf_life_snapshot,
          item_shelf_life_value_snapshot,
          item_shelf_life_unit_snapshot,
          item_uom_snapshot,
          item_case_ratio_snapshot,
          item_case_uom_snapshot,
          item_lot_source_policy_snapshot,
          item_expiry_policy_snapshot,
          item_derivation_allowed_snapshot,
          item_uom_governance_enabled_snapshot
        )
        SELECT
          k.warehouse_id,
          k.item_id,
          'SUPPLIER',
          k.lot_code,
          NULL,
          NULL,
          now(),
          it.has_shelf_life,
          it.shelf_life_value,
          it.shelf_life_unit,
          it.uom,
          it.case_ratio,
          it.case_uom,
          it.lot_source_policy,
          it.expiry_policy,
          it.derivation_allowed,
          it.uom_governance_enabled
        FROM keys k
        JOIN public.items it ON it.id = k.item_id
        ON CONFLICT (warehouse_id, item_id, lot_code) WHERE lot_code IS NOT NULL
        DO NOTHING
        """
    )

    # 1.2) Create INTERNAL "snapshot slot" lots for NULL batch_code in stock_snapshots (one per wh+item)
    op.execute(
        """
        WITH keys AS (
          SELECT DISTINCT warehouse_id, item_id
          FROM public.stock_snapshots
          WHERE batch_code IS NULL
        )
        INSERT INTO public.lots(
          warehouse_id, item_id, lot_code_source, lot_code,
          source_receipt_id, source_line_no,
          created_at,
          item_has_shelf_life_snapshot,
          item_shelf_life_value_snapshot,
          item_shelf_life_unit_snapshot,
          item_uom_snapshot,
          item_case_ratio_snapshot,
          item_case_uom_snapshot,
          item_lot_source_policy_snapshot,
          item_expiry_policy_snapshot,
          item_derivation_allowed_snapshot,
          item_uom_governance_enabled_snapshot
        )
        SELECT
          k.warehouse_id,
          k.item_id,
          'INTERNAL',
          'INTERNAL-SNAPSHOT',
          NULL,
          NULL,
          now(),
          it.has_shelf_life,
          it.shelf_life_value,
          it.shelf_life_unit,
          it.uom,
          it.case_ratio,
          it.case_uom,
          it.lot_source_policy,
          it.expiry_policy,
          it.derivation_allowed,
          it.uom_governance_enabled
        FROM keys k
        JOIN public.items it ON it.id = k.item_id
        ON CONFLICT (warehouse_id, item_id, lot_code) WHERE lot_code IS NOT NULL
        DO NOTHING
        """
    )

    # ------------------------------------------------------------
    # 2) Backfill lot_id in both tables
    # ------------------------------------------------------------
    op.execute(
        """
        UPDATE public.stock_snapshots ss
        SET lot_id = lo.id
        FROM public.lots lo
        WHERE lo.warehouse_id = ss.warehouse_id
          AND lo.item_id = ss.item_id
          AND (
            (ss.batch_code IS NOT NULL AND lo.lot_code_source='SUPPLIER' AND lo.lot_code = ss.batch_code)
            OR
            (ss.batch_code IS NULL AND lo.lot_code_source='INTERNAL' AND lo.lot_code = 'INTERNAL-SNAPSHOT')
          )
        """
    )

    op.execute(
        """
        UPDATE public.snapshots s
        SET lot_id = lo.id
        FROM public.lots lo
        WHERE lo.warehouse_id = s.warehouse_id
          AND lo.item_id = s.item_id
          AND lo.lot_code_source='SUPPLIER'
          AND lo.lot_code = s.batch_code
        """
    )

    # ------------------------------------------------------------
    # 3) Fail-fast if any NULL remains
    # ------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM public.stock_snapshots WHERE lot_id IS NULL) THEN
            RAISE EXCEPTION 'stock_snapshots.lot_id backfill failed: NULL lot_id remains';
          END IF;
          IF EXISTS (SELECT 1 FROM public.snapshots WHERE lot_id IS NULL) THEN
            RAISE EXCEPTION 'snapshots.lot_id backfill failed: NULL lot_id remains';
          END IF;
        END $$;
        """
    )

    # ------------------------------------------------------------
    # 4) Enforce lot-world grain on stock_snapshots
    # ------------------------------------------------------------
    op.drop_constraint("uq_stock_snapshot_grain_v2", "stock_snapshots", type_="unique")
    op.execute("DROP INDEX IF EXISTS public.ix_stock_snapshots_batch_code_key")

    with op.batch_alter_table("stock_snapshots") as bop:
        bop.alter_column("lot_id", nullable=False)
        # drop generated column first, then batch_code
        bop.drop_column("batch_code_key")
        bop.drop_column("batch_code")

    op.create_foreign_key(
        "fk_stock_snapshots_lot_dims",
        "stock_snapshots",
        "lots",
        ["lot_id", "warehouse_id", "item_id"],
        ["id", "warehouse_id", "item_id"],
        ondelete="RESTRICT",
    )

    op.create_unique_constraint(
        "uq_stock_snapshots_grain_lot",
        "stock_snapshots",
        ["snapshot_date", "warehouse_id", "item_id", "lot_id"],
    )

    op.create_index("ix_stock_snapshots_lot_id", "stock_snapshots", ["lot_id"])
    op.create_index("ix_stock_snapshots_wh_item_lot", "stock_snapshots", ["warehouse_id", "item_id", "lot_id"])

    # ------------------------------------------------------------
    # 5) Enforce lot-world grain on snapshots
    # ------------------------------------------------------------
    op.drop_constraint("uq_snapshots_date_wh_item_code", "snapshots", type_="unique")
    op.execute("DROP INDEX IF EXISTS public.ix_snapshots_batch_code")

    with op.batch_alter_table("snapshots") as bop:
        bop.alter_column("lot_id", nullable=False)
        bop.drop_column("batch_code")

    op.create_foreign_key(
        "fk_snapshots_lot_dims",
        "snapshots",
        "lots",
        ["lot_id", "warehouse_id", "item_id"],
        ["id", "warehouse_id", "item_id"],
        ondelete="RESTRICT",
    )

    op.create_unique_constraint(
        "uq_snapshots_grain_lot",
        "snapshots",
        ["snapshot_date", "warehouse_id", "item_id", "lot_id"],
    )

    op.create_index("ix_snapshots_lot_id", "snapshots", ["lot_id"])
    op.create_index("ix_snapshots_wh_item_lot", "snapshots", ["warehouse_id", "item_id", "lot_id"])


def downgrade() -> None:
    raise NotImplementedError("One-way migration: batch->lot snapshot grain is not safely reversible.")
