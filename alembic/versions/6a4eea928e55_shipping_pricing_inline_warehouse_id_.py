"""shipping pricing: inline warehouse_id into schemes and drop scheme_warehouses

Revision ID: 6a4eea928e55
Revises: 70144e0014e5
Create Date: 2026-03-05 19:48:37.792584

- Move warehouse binding from shipping_provider_pricing_scheme_warehouses into
  shipping_provider_pricing_schemes.warehouse_id (hard warehouse scope).
- Replace unique constraint:
    old: one active scheme per provider
    new: one active scheme per (warehouse, provider)
- Drop mapping table to eliminate dual "active" drift.
- Delete known orphan/ambiguous legacy schemes (381, 448) that cannot be assigned deterministically.

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6a4eea928e55"
down_revision: Union[str, Sequence[str], None] = "70144e0014e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) add warehouse_id nullable first (so we can backfill safely)
    op.add_column(
        "shipping_provider_pricing_schemes",
        sa.Column("warehouse_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_sp_pricing_schemes_warehouse_id",
        "shipping_provider_pricing_schemes",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 2) backfill from mapping table (direct binding)
    op.execute(
        """
        UPDATE shipping_provider_pricing_schemes sch
           SET warehouse_id = spsw.warehouse_id
          FROM shipping_provider_pricing_scheme_warehouses spsw
         WHERE spsw.scheme_id = sch.id
        """
    )

    # 3) deterministic fallback for orphan schemes:
    #    if a provider appears in mapping table with exactly ONE distinct warehouse_id,
    #    then any orphan scheme for that provider can be safely assigned to that warehouse.
    #    (No ambiguity => no drift.)
    op.execute(
        """
        WITH provider_single_warehouse AS (
          SELECT
            sch2.shipping_provider_id AS shipping_provider_id,
            MIN(spsw.warehouse_id)     AS warehouse_id
          FROM shipping_provider_pricing_scheme_warehouses spsw
          JOIN shipping_provider_pricing_schemes sch2
            ON sch2.id = spsw.scheme_id
          GROUP BY sch2.shipping_provider_id
          HAVING COUNT(DISTINCT spsw.warehouse_id) = 1
        )
        UPDATE shipping_provider_pricing_schemes sch
           SET warehouse_id = psw.warehouse_id
          FROM provider_single_warehouse psw
         WHERE sch.warehouse_id IS NULL
           AND sch.shipping_provider_id = psw.shipping_provider_id
        """
    )

    # 4) delete known orphan/ambiguous legacy schemes (garbage) that cannot be assigned deterministically.
    #    Reason: schemes without warehouse binding are invalid under Route A.
    #    Note: some child tables use ON DELETE RESTRICT, so we must delete children first.
    op.execute(
        """
        -- delete zone children first (RESTRICT)
        WITH doomed AS (
          SELECT unnest(ARRAY[381,448]::int[]) AS scheme_id
        ),
        doomed_zones AS (
          SELECT z.id AS zone_id
            FROM shipping_provider_zones z
            JOIN doomed d ON d.scheme_id = z.scheme_id
        )
        DELETE FROM shipping_provider_zone_brackets
         WHERE zone_id IN (SELECT zone_id FROM doomed_zones);

        WITH doomed AS (
          SELECT unnest(ARRAY[381,448]::int[]) AS scheme_id
        ),
        doomed_zones AS (
          SELECT z.id AS zone_id
            FROM shipping_provider_zones z
            JOIN doomed d ON d.scheme_id = z.scheme_id
        )
        DELETE FROM shipping_provider_zone_members
         WHERE zone_id IN (SELECT zone_id FROM doomed_zones);

        WITH doomed AS (
          SELECT unnest(ARRAY[381,448]::int[]) AS scheme_id
        )
        DELETE FROM shipping_provider_zones
         WHERE scheme_id IN (SELECT scheme_id FROM doomed);

        -- surcharges FK is ON DELETE RESTRICT, delete explicitly
        WITH doomed AS (
          SELECT unnest(ARRAY[381,448]::int[]) AS scheme_id
        )
        DELETE FROM shipping_provider_surcharges
         WHERE scheme_id IN (SELECT scheme_id FROM doomed);

        -- dest_adjustments is ON DELETE CASCADE; segments/templates usually cascade as well.
        -- finally delete schemes
        WITH doomed AS (
          SELECT unnest(ARRAY[381,448]::int[]) AS scheme_id
        )
        DELETE FROM shipping_provider_pricing_schemes
         WHERE id IN (SELECT scheme_id FROM doomed);
        """
    )

    # 5) assert no NULL after backfill (fail fast, and show which scheme_ids are ambiguous/orphan)
    op.execute(
        """
        DO $$
        DECLARE
          ids text;
        BEGIN
          SELECT string_agg(id::text, ',')
            INTO ids
          FROM shipping_provider_pricing_schemes
          WHERE warehouse_id IS NULL;

          IF ids IS NOT NULL THEN
            RAISE EXCEPTION
              'migration failed: schemes.warehouse_id still NULL after backfill. orphan/ambiguous scheme_ids=%',
              ids;
          END IF;
        END $$;
        """
    )

    # 6) set NOT NULL
    op.alter_column("shipping_provider_pricing_schemes", "warehouse_id", nullable=False)

    # 7) replace unique:
    #    drop old partial unique (provider-only)
    #    create new partial unique (warehouse+provider)
    op.drop_index(
        "uq_pricing_schemes_one_active_per_provider",
        table_name="shipping_provider_pricing_schemes",
        postgresql_where=sa.text("(active IS TRUE) AND (archived_at IS NULL)"),
    )

    op.create_index(
        "uq_pricing_schemes_one_active_per_wh_provider",
        "shipping_provider_pricing_schemes",
        ["warehouse_id", "shipping_provider_id"],
        unique=True,
        postgresql_where=sa.text("(active IS TRUE) AND (archived_at IS NULL)"),
    )

    # helpful lookup index (cheap)
    op.create_index(
        "ix_sp_pricing_schemes_wh_provider_active",
        "shipping_provider_pricing_schemes",
        ["warehouse_id", "shipping_provider_id", "active"],
        unique=False,
    )

    # 8) drop mapping table (eliminate dual-active drift)
    op.drop_table("shipping_provider_pricing_scheme_warehouses")


def downgrade() -> None:
    # 1) recreate mapping table
    op.create_table(
        "shipping_provider_pricing_scheme_warehouses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("scheme_id", "warehouse_id", name="uq_sp_scheme_wh_scheme_warehouse"),
    )
    op.create_foreign_key(
        "fk_sp_scheme_wh_scheme_id",
        "shipping_provider_pricing_scheme_warehouses",
        "shipping_provider_pricing_schemes",
        ["scheme_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_sp_scheme_wh_warehouse_id",
        "shipping_provider_pricing_scheme_warehouses",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_sp_scheme_wh_scheme_id",
        "shipping_provider_pricing_scheme_warehouses",
        ["scheme_id"],
        unique=False,
    )
    op.create_index(
        "ix_sp_scheme_wh_warehouse_id",
        "shipping_provider_pricing_scheme_warehouses",
        ["warehouse_id"],
        unique=False,
    )
    op.create_index(
        "ix_sp_scheme_wh_active",
        "shipping_provider_pricing_scheme_warehouses",
        ["active"],
        unique=False,
    )

    # 2) backfill mapping table from schemes.warehouse_id
    op.execute(
        """
        INSERT INTO shipping_provider_pricing_scheme_warehouses (scheme_id, warehouse_id, active)
        SELECT id, warehouse_id, true
          FROM shipping_provider_pricing_schemes
        """
    )

    # 3) drop new indexes/unique
    op.drop_index("ix_sp_pricing_schemes_wh_provider_active", table_name="shipping_provider_pricing_schemes")
    op.drop_index(
        "uq_pricing_schemes_one_active_per_wh_provider",
        table_name="shipping_provider_pricing_schemes",
        postgresql_where=sa.text("(active IS TRUE) AND (archived_at IS NULL)"),
    )

    # 4) restore old unique (provider-only)
    op.create_index(
        "uq_pricing_schemes_one_active_per_provider",
        "shipping_provider_pricing_schemes",
        ["shipping_provider_id"],
        unique=True,
        postgresql_where=sa.text("(active IS TRUE) AND (archived_at IS NULL)"),
    )

    # 5) drop FK + column warehouse_id
    op.drop_constraint("fk_sp_pricing_schemes_warehouse_id", "shipping_provider_pricing_schemes", type_="foreignkey")
    op.drop_column("shipping_provider_pricing_schemes", "warehouse_id")
