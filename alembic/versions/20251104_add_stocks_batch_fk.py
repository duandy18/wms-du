"""Add stocks.batch_id FK and migrate unique to (item_id, location_id, batch_id)

Revision ID: 20251104_add_stocks_batch_fk
Revises: 20251104_merge_scan_views_heads
Create Date: 2025-11-04 20:30:00
"""

from __future__ import annotations

from typing import Optional, Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# ---- Alembic identifiers ----
revision: str = "20251104_add_stocks_batch_fk"
down_revision: Optional[str] = "20251104_merge_scan_views_heads"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None
# -----------------------------


def _get_inspector(conn) -> Inspector:
    return sa.inspect(conn)


def _has_column(inspector: Inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


def _get_unique_constraint_by_cols(
    inspector: Inspector, table: str, cols: set[str]
) -> Optional[str]:
    for uc in inspector.get_unique_constraints(table):
        if set(uc.get("column_names") or []) == cols:
            return uc["name"]
    return None


def upgrade():
    conn = op.get_bind()
    insp = _get_inspector(conn)

    # 1) add column batch_id (nullable first) + index
    if not _has_column(insp, "stocks", "batch_id"):
        op.add_column("stocks", sa.Column("batch_id", sa.BigInteger(), nullable=True))
        op.create_index("ix_stocks_batch_id", "stocks", ["batch_id"])
    else:
        indexes = {ix["name"] for ix in insp.get_indexes("stocks")}
        if "ix_stocks_batch_id" not in indexes:
            op.create_index("ix_stocks_batch_id", "stocks", ["batch_id"])

    # 2) create AUTO batches per (item, location) using warehouse from locations
    conn.execute(
        sa.text("""
        INSERT INTO batches (item_id, warehouse_id, location_id, batch_code)
        SELECT DISTINCT s.item_id, loc.warehouse_id, s.location_id,
               'AUTO-' || s.item_id || '-' || s.location_id AS batch_code
          FROM stocks s
          JOIN locations loc ON loc.id = s.location_id
          LEFT JOIN batches b
                 ON b.item_id = s.item_id
                AND b.location_id = s.location_id
                AND b.warehouse_id = loc.warehouse_id
                AND b.batch_code = 'AUTO-' || s.item_id || '-' || s.location_id
         WHERE b.id IS NULL
        ON CONFLICT (item_id, warehouse_id, location_id, batch_code) DO NOTHING;
    """)
    )

    # 3) backfill stocks.batch_id from created AUTO batches
    #    关键修复：不能在 FROM 的 JOIN ... ON 中引用 UPDATE 目标别名 s
    #    因此把对 s 的引用放入 WHERE 子句
    conn.execute(
        sa.text("""
        UPDATE stocks s
           SET batch_id = b.id
          FROM batches b, locations loc
         WHERE s.batch_id IS NULL
           AND loc.id = s.location_id
           AND b.item_id = s.item_id
           AND b.location_id = s.location_id
           AND b.warehouse_id = loc.warehouse_id
           AND b.batch_code = 'AUTO-' || s.item_id || '-' || s.location_id;
    """)
    )

    # 4) switch unique constraints
    old_uc = _get_unique_constraint_by_cols(insp, "stocks", {"item_id", "location_id"})
    if old_uc:
        op.drop_constraint(old_uc, "stocks", type_="unique")
    new_uc_name = _get_unique_constraint_by_cols(
        insp, "stocks", {"item_id", "location_id", "batch_id"}
    )
    if not new_uc_name:
        op.create_unique_constraint(
            "uq_stocks_item_loc_batch",
            "stocks",
            ["item_id", "location_id", "batch_id"],
        )

    # 5) create FK stocks.batch_id → batches.id (ondelete CASCADE)
    fks = insp.get_foreign_keys("stocks")
    if not any(
        fk.get("constrained_columns") == ["batch_id"] and fk.get("referred_table") == "batches"
        for fk in fks
    ):
        op.create_foreign_key(
            "fk_stocks_batch_id_batches",
            "stocks",
            "batches",
            local_cols=["batch_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )

    # 6) set NOT NULL after backfill
    op.alter_column("stocks", "batch_id", nullable=False)


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # 1) allow NULL again
    if _has_column(insp, "stocks", "batch_id"):
        op.alter_column("stocks", "batch_id", nullable=True)

    # 2) drop FK
    for fk in insp.get_foreign_keys("stocks"):
        if fk.get("constrained_columns") == ["batch_id"] and fk.get("referred_table") == "batches":
            op.drop_constraint(fk["name"], "stocks", type_="foreignkey")
            break

    # 3) drop new unique (item, location, batch_id)
    uc = _get_unique_constraint_by_cols(insp, "stocks", {"item_id", "location_id", "batch_id"})
    if uc:
        op.drop_constraint(uc, "stocks", type_="unique")

    # 4) restore old unique (item, location)
    old_uc = _get_unique_constraint_by_cols(insp, "stocks", {"item_id", "location_id"})
    if not old_uc:
        op.create_unique_constraint("uq_stock_item_location", "stocks", ["item_id", "location_id"])

    # 5) drop index & column
    indexes = {ix["name"] for ix in insp.get_indexes("stocks")}
    if "ix_stocks_batch_id" in indexes:
        op.drop_index("ix_stocks_batch_id", table_name="stocks")
    if _has_column(insp, "stocks", "batch_id"):
        op.drop_column("stocks", "batch_id")
