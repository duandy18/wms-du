"""add_level3_pricing_matrix_tables

Revision ID: c50075adba75
Revises: 118d1fcd038b
Create Date: 2026-03-06

Level-3 运价矩阵模型：
destination_groups
destination_group_members
pricing_matrix
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "c50075adba75"
down_revision: Union[str, Sequence[str], None] = "118d1fcd038b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # =========================================================
    # 1) destination groups（目的地收费组）
    # =========================================================

    op.create_table(
        "shipping_provider_destination_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            name="fk_sp_dest_groups_scheme_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("scheme_id", "name", name="uq_sp_dest_groups_scheme_name"),
    )

    op.create_index(
        "ix_sp_dest_groups_scheme",
        "shipping_provider_destination_groups",
        ["scheme_id"],
    )

    op.create_index(
        "ix_sp_dest_groups_scheme_active",
        "shipping_provider_destination_groups",
        ["scheme_id", "active"],
    )

    # =========================================================
    # 2) destination group members
    # =========================================================

    op.create_table(
        "shipping_provider_destination_group_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), nullable=False),

        sa.Column("scope", sa.String(length=16), nullable=False),

        sa.Column("province_code", sa.String(length=32), nullable=True),
        sa.Column("city_code", sa.String(length=32), nullable=True),

        sa.Column("province_name", sa.String(length=64), nullable=True),
        sa.Column("city_name", sa.String(length=64), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(
            ["group_id"],
            ["shipping_provider_destination_groups.id"],
            name="fk_sp_dest_group_members_group_id",
            ondelete="CASCADE",
        ),

        sa.CheckConstraint(
            "scope in ('province','city')",
            name="ck_sp_dest_group_members_scope_valid",
        ),

        sa.CheckConstraint(
            """
            (
              scope = 'province'
              AND (province_name IS NOT NULL OR province_code IS NOT NULL)
              AND city_name IS NULL
              AND city_code IS NULL
            )
            OR
            (
              scope = 'city'
              AND (province_name IS NOT NULL OR province_code IS NOT NULL)
              AND (city_name IS NOT NULL OR city_code IS NOT NULL)
            )
            """,
            name="ck_sp_dest_group_members_scope_fields",
        ),
    )

    op.create_index(
        "ix_spdgm_group",
        "shipping_provider_destination_group_members",
        ["group_id"],
    )

    op.create_index(
        "ix_spdgm_scope_province",
        "shipping_provider_destination_group_members",
        ["scope", "province_code", "province_name"],
    )

    op.create_index(
        "ix_spdgm_scope_city",
        "shipping_provider_destination_group_members",
        ["scope", "province_code", "city_code", "province_name", "city_name"],
    )

    op.create_index(
        "uq_spdgm_group_scope_key",
        "shipping_provider_destination_group_members",
        [
            sa.text("group_id"),
            sa.text("scope"),
            sa.text("COALESCE(province_code,'')"),
            sa.text("COALESCE(city_code,'')"),
            sa.text("COALESCE(province_name,'')"),
            sa.text("COALESCE(city_name,'')")
        ],
        unique=True,
    )

    # =========================================================
    # 3) pricing matrix
    # =========================================================

    op.create_table(
        "shipping_provider_pricing_matrix",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), nullable=False),

        sa.Column("min_kg", sa.Numeric(10, 3), nullable=False),
        sa.Column("max_kg", sa.Numeric(10, 3), nullable=True),

        sa.Column("pricing_mode", sa.String(length=32), nullable=False),

        sa.Column("flat_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("rate_per_kg", sa.Numeric(12, 4), nullable=True),
        sa.Column("base_kg", sa.Numeric(10, 3), nullable=True),

        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(
            ["group_id"],
            ["shipping_provider_destination_groups.id"],
            name="fk_sp_pricing_matrix_group_id",
            ondelete="CASCADE",
        ),

        sa.CheckConstraint(
            "min_kg >= 0 AND (max_kg IS NULL OR max_kg > min_kg)",
            name="ck_sppm_range_valid",
        ),

        sa.CheckConstraint(
            "pricing_mode in ('flat','linear_total','step_over','manual_quote')",
            name="ck_sppm_mode_valid",
        ),

        sa.CheckConstraint(
            "pricing_mode <> 'flat' OR flat_amount IS NOT NULL",
            name="ck_sppm_flat_needs_flat_amount",
        ),

        sa.CheckConstraint(
            "pricing_mode <> 'linear_total' OR rate_per_kg IS NOT NULL",
            name="ck_sppm_linear_needs_rate",
        ),

        sa.CheckConstraint(
            """
            pricing_mode <> 'step_over'
            OR (
                base_kg IS NOT NULL
                AND base_amount IS NOT NULL
                AND rate_per_kg IS NOT NULL
            )
            """,
            name="ck_sppm_step_over_needs_fields",
        ),
    )

    op.create_index(
        "ix_sppm_group",
        "shipping_provider_pricing_matrix",
        ["group_id"],
    )

    op.create_index(
        "ix_sppm_group_active_min",
        "shipping_provider_pricing_matrix",
        ["group_id", "active", "min_kg"],
    )

    op.create_index(
        "uq_sppm_group_min_max_coalesced",
        "shipping_provider_pricing_matrix",
        [
            sa.text("group_id"),
            sa.text("min_kg"),
            sa.text("COALESCE(max_kg,999999.000)")
        ],
        unique=True,
    )

    # =========================================================
    # exclusion constraint (防重叠区间)
    # =========================================================

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        ADD CONSTRAINT excl_sppm_active_group_weight_range_no_overlap
        EXCLUDE USING gist (
            group_id WITH =,
            numrange(min_kg, max_kg, '[)') WITH &&
        )
        WHERE (active)
        """
    )


def downgrade() -> None:

    op.execute(
        """
        ALTER TABLE shipping_provider_pricing_matrix
        DROP CONSTRAINT IF EXISTS excl_sppm_active_group_weight_range_no_overlap
        """
    )

    op.drop_index("uq_sppm_group_min_max_coalesced", table_name="shipping_provider_pricing_matrix")
    op.drop_index("ix_sppm_group_active_min", table_name="shipping_provider_pricing_matrix")
    op.drop_index("ix_sppm_group", table_name="shipping_provider_pricing_matrix")

    op.drop_table("shipping_provider_pricing_matrix")

    op.drop_index("uq_spdgm_group_scope_key", table_name="shipping_provider_destination_group_members")
    op.drop_index("ix_spdgm_scope_city", table_name="shipping_provider_destination_group_members")
    op.drop_index("ix_spdgm_scope_province", table_name="shipping_provider_destination_group_members")
    op.drop_index("ix_spdgm_group", table_name="shipping_provider_destination_group_members")

    op.drop_table("shipping_provider_destination_group_members")

    op.drop_index("ix_sp_dest_groups_scheme_active", table_name="shipping_provider_destination_groups")
    op.drop_index("ix_sp_dest_groups_scheme", table_name="shipping_provider_destination_groups")

    op.drop_table("shipping_provider_destination_groups")
