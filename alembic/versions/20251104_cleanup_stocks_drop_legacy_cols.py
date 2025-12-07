"""Cleanup stocks: converge uniques/indexes only (keep legacy columns for dependent views)

Revision ID: 20251104_cleanup_stocks_drop_legacy_cols
Revises: 20251104_add_stocks_batch_fk
Create Date: 2025-11-04 22:10:00
"""

from __future__ import annotations

from typing import Optional, Sequence

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision: str = "20251104_cleanup_stocks_drop_legacy_cols"
down_revision: Optional[str] = "20251104_add_stocks_batch_fk"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None
# -----------------------------


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    def drop_uc_if(cols: set[str]):
        """Drop unique constraint on stocks if exact column set matches."""
        for uc in insp.get_unique_constraints("stocks"):
            if set(uc.get("column_names") or []) == cols:
                op.drop_constraint(uc["name"], "stocks", type_="unique")
                return True
        return False

    def ensure_idx(name: str, cols: list[str]):
        """Ensure a btree index exists on given columns."""
        existing = {ix["name"] for ix in insp.get_indexes("stocks")}
        if name not in existing:
            op.create_index(name, "stocks", cols)

    def drop_index_if(name: str):
        existing = {ix["name"] for ix in insp.get_indexes("stocks")}
        if name in existing:
            op.drop_index(name, table_name="stocks")

    # 0) Ensure target unique (item_id, location_id, batch_id) exists
    if not any(
        set(uc.get("column_names") or []) == {"item_id", "location_id", "batch_id"}
        for uc in insp.get_unique_constraints("stocks")
    ):
        op.create_unique_constraint(
            "uq_stocks_item_loc_batch",
            "stocks",
            ["item_id", "location_id", "batch_id"],
        )

    # 1) Drop legacy uniques that conflict with the new single-source-of-truth
    #    - (item_id, location_id, batch_code)
    #    - (item_id, warehouse_id, location_id, batch_code)
    drop_uc_if({"item_id", "location_id", "batch_code"})
    drop_uc_if({"item_id", "warehouse_id", "location_id", "batch_code"})

    # 2) Deduplicate (item_id, location_id) indexes — keep exactly one
    #    You currently have: idx_stocks_i_l, ix_stock_item_loc, ix_stocks_item_loc
    #    We keep ix_stocks_item_loc and drop the other two if present.
    ensure_idx("ix_stocks_item_loc", ["item_id", "location_id"])
    drop_index_if("idx_stocks_i_l")
    drop_index_if("ix_stock_item_loc")

    # NOTE:
    # We intentionally DO NOT drop legacy columns:
    #   - stocks.batch_code
    #   - stocks.warehouse_id
    # because dependent views (e.g., v_putaway_ledger_recent) still reference them.
    # After views are rewritten to use:
    #   - batches.batch_code
    #   - locations.warehouse_id
    # we will follow up with a tiny migration to DROP those columns safely.


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # Recreate the legacy uniques if they don't exist (weak rollback)
    ucs = {uc["name"] for uc in insp.get_unique_constraints("stocks")}
    if "uq_stocks_item_loc_code" not in ucs:
        op.create_unique_constraint(
            "uq_stocks_item_loc_code",
            "stocks",
            ["item_id", "location_id", "batch_code"],
        )
    if "uq_stocks_item_wh_loc_code" not in ucs:
        op.create_unique_constraint(
            "uq_stocks_item_wh_loc_code",
            "stocks",
            ["item_id", "warehouse_id", "location_id", "batch_code"],
        )

    # Recreate duplicate indexes for rollback symmetry
    existing = {ix["name"] for ix in insp.get_indexes("stocks")}
    if "idx_stocks_i_l" not in existing:
        op.create_index("idx_stocks_i_l", "stocks", ["item_id", "location_id"])
    if "ix_stock_item_loc" not in existing:
        op.create_index("ix_stock_item_loc", "stocks", ["item_id", "location_id"])
    # Keep ix_stocks_item_loc as well; duplicates are intentional for downgrade symmetry
