"""dest adjustments add codes

Revision ID: 1cc94f14a0fa
Revises: 54e1cf6ab525
Create Date: 2026-01-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1cc94f14a0fa"
down_revision = "54e1cf6ab525"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) add new columns (nullable first for safe backfill)
    op.add_column(
        "pricing_scheme_dest_adjustments",
        sa.Column("province_code", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "pricing_scheme_dest_adjustments",
        sa.Column("city_code", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "pricing_scheme_dest_adjustments",
        sa.Column("province_name", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "pricing_scheme_dest_adjustments",
        sa.Column("city_name", sa.String(length=64), nullable=True),
    )

    # 2) backfill (minimal safe strategy)
    #    - use legacy province/city as code+name for now
    #    - real stability will come after FE switches to real codes
    op.execute(
        """
        UPDATE pricing_scheme_dest_adjustments
        SET
          province_code = COALESCE(NULLIF(BTRIM(province_code), ''), NULLIF(BTRIM(province), '')),
          city_code = COALESCE(NULLIF(BTRIM(city_code), ''), NULLIF(BTRIM(city), '')),
          province_name = COALESCE(NULLIF(BTRIM(province_name), ''), NULLIF(BTRIM(province), '')),
          city_name = COALESCE(NULLIF(BTRIM(city_name), ''), NULLIF(BTRIM(city), ''))
        """
    )

    # 3) make province_code NOT NULL (after backfill)
    op.alter_column(
        "pricing_scheme_dest_adjustments",
        "province_code",
        existing_type=sa.String(length=32),
        nullable=False,
    )

    # 4) switch unique constraint to code-based key
    #    old: uq_scheme_dest_adj_scope_province_city (scheme_id, scope, province, city)
    #    new: uq_scheme_dest_adj_scope_provcode_citycode (scheme_id, scope, province_code, city_code)
    op.drop_constraint(
        "uq_scheme_dest_adj_scope_province_city",
        "pricing_scheme_dest_adjustments",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_scheme_dest_adj_scope_provcode_citycode",
        "pricing_scheme_dest_adjustments",
        ["scheme_id", "scope", "province_code", "city_code"],
    )


def downgrade() -> None:
    # rollback unique constraint
    op.drop_constraint(
        "uq_scheme_dest_adj_scope_provcode_citycode",
        "pricing_scheme_dest_adjustments",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_scheme_dest_adj_scope_province_city",
        "pricing_scheme_dest_adjustments",
        ["scheme_id", "scope", "province", "city"],
    )

    # loosen province_code
    op.alter_column(
        "pricing_scheme_dest_adjustments",
        "province_code",
        existing_type=sa.String(length=32),
        nullable=True,
    )

    # drop columns
    op.drop_column("pricing_scheme_dest_adjustments", "city_name")
    op.drop_column("pricing_scheme_dest_adjustments", "province_name")
    op.drop_column("pricing_scheme_dest_adjustments", "city_code")
    op.drop_column("pricing_scheme_dest_adjustments", "province_code")
