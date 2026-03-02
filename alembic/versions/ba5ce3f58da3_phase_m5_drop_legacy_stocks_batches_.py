"""phase m5: drop legacy stocks/batches tables

Revision ID: ba5ce3f58da3
Revises: 9cf0a8ecc208
Create Date: 2026-03-02 11:42:03.813634

Lot-World invariant:
- stocks_lot is the only inventory fact table
- stock_ledger anchors on lot_id
- legacy tables (stocks, batches) must be physically removed

This migration is defensive / idempotent across environments:
- constraint names may differ
- some envs may already have dropped legacy objects

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ba5ce3f58da3"
down_revision: Union[str, Sequence[str], None] = "9cf0a8ecc208"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(insp: sa.Inspector, name: str) -> bool:
    return bool(insp.has_table(name, schema="public"))


def _has_column(insp: sa.Inspector, table: str, col: str) -> bool:
    return any(c.get("name") == col for c in insp.get_columns(table, schema="public"))


def _find_fk_name_locations_current_batch(insp: sa.Inspector) -> str | None:
    """
    Return FK constraint name on locations(current_batch_id) -> batches(id), if present.
    Name may not be stable across envs.
    """
    if not _has_table(insp, "locations"):
        return None
    for fk in insp.get_foreign_keys("locations", schema="public"):
        cols = fk.get("constrained_columns") or []
        if cols == ["current_batch_id"] and fk.get("referred_table") == "batches":
            return fk.get("name")
    return None


def upgrade() -> None:
    """Upgrade schema: remove legacy stocks/batches."""

    conn = op.get_bind()
    insp = sa.inspect(conn)

    # ---- 0) best-effort: drop views depending on stocks/batches (avoid DependentObjectsStillExist) ----
    conn.execute(
        sa.text(
            """
            DO $$
            DECLARE
              r record;
            BEGIN
              FOR r IN
                SELECT schemaname, viewname
                FROM pg_views
                WHERE schemaname = 'public'
                  AND (definition ILIKE '% stocks %' OR definition ILIKE '% batches %')
              LOOP
                EXECUTE format('DROP VIEW IF EXISTS %I.%I CASCADE', r.schemaname, r.viewname);
              END LOOP;
            END $$;
            """
        )
    )

    # ---- 1) break locations -> batches dependency (if any) ----
    if _has_table(insp, "locations") and _has_column(insp, "locations", "current_batch_id"):
        fk_name = _find_fk_name_locations_current_batch(insp)
        if fk_name:
            op.drop_constraint(fk_name, "locations", type_="foreignkey")
        # even if FK missing, drop the column if it exists
        op.drop_column("locations", "current_batch_id")

    # ---- 2) drop legacy tables (if they exist) ----
    # Drop stocks first (it may depend on batches)
    if _has_table(insp, "stocks"):
        op.drop_table("stocks")

    if _has_table(insp, "batches"):
        op.drop_table("batches")


def downgrade() -> None:
    """Downgrade schema: best-effort minimal restore of legacy tables.

    Note: this is a minimal placeholder, not a full historical reconstruction.
    """

    op.create_table(
        "batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
    )

    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["batches.id"],
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    # Restore locations.current_batch_id only if locations table exists
    # (some envs may have removed locations entirely).
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if _has_table(insp, "locations") and not _has_column(insp, "locations", "current_batch_id"):
        op.add_column("locations", sa.Column("current_batch_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_locations_current_batch",
            "locations",
            "batches",
            ["current_batch_id"],
            ["id"],
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        )
