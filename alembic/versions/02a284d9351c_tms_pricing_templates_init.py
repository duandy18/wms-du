"""tms_pricing_templates_init

Revision ID: 02a284d9351c
Revises: 609bf0fd9500
Create Date: 2026-03-20 12:55:37.757305
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "02a284d9351c"
down_revision: Union[str, Sequence[str], None] = "609bf0fd9500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shipping_provider_pricing_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("shipping_provider_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "default_pricing_mode",
            sa.String(length=32),
            nullable=False,
            server_default="linear_total",
        ),
        sa.Column(
            "billable_weight_strategy",
            sa.String(length=32),
            nullable=False,
            server_default="actual_only",
        ),
        sa.Column("volume_divisor", sa.Integer(), nullable=True),
        sa.Column(
            "rounding_mode",
            sa.String(length=16),
            nullable=False,
            server_default="none",
        ),
        sa.Column("rounding_step_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("min_billable_weight_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["shipping_provider_id"],
            ["shipping_providers.id"],
            ondelete="RESTRICT",
            name="fk_sppt_provider_id",
        ),
        sa.CheckConstraint(
            "status in ('draft','active','archived')",
            name="ck_sppt_status_valid",
        ),
        sa.CheckConstraint(
            "billable_weight_strategy in ('actual_only','max_actual_volume')",
            name="ck_sppt_billable_strategy",
        ),
        sa.CheckConstraint(
            "rounding_mode in ('none','ceil')",
            name="ck_sppt_rounding_mode",
        ),
        sa.CheckConstraint(
            "default_pricing_mode in ('flat','linear_total','step_over','manual_quote')",
            name="ck_sppt_default_pricing_mode",
        ),
    )

    op.create_table(
        "shipping_provider_pricing_template_module_ranges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("min_kg", sa.Numeric(10, 3), nullable=False),
        sa.Column("max_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "default_pricing_mode",
            sa.String(length=32),
            nullable=False,
            server_default="flat",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["shipping_provider_pricing_templates.id"],
            ondelete="CASCADE",
            name="fk_spptmr_template_id",
        ),
        sa.CheckConstraint(
            "min_kg >= 0 AND (max_kg IS NULL OR max_kg > min_kg)",
            name="ck_spptmr_range_valid",
        ),
        sa.CheckConstraint(
            "default_pricing_mode in ('flat','linear_total','step_over','manual_quote')",
            name="ck_spptmr_default_mode_valid",
        ),
        sa.UniqueConstraint(
            "template_id",
            "sort_order",
            name="uq_spptmr_template_sort_order",
        ),
        sa.UniqueConstraint(
            "template_id",
            "min_kg",
            "max_kg",
            name="uq_spptmr_template_range",
        ),
    )
    op.create_index(
        "ix_spptmr_template_id",
        "shipping_provider_pricing_template_module_ranges",
        ["template_id"],
        unique=False,
    )

    op.create_table(
        "shipping_provider_pricing_template_destination_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["shipping_provider_pricing_templates.id"],
            ondelete="CASCADE",
            name="fk_spptdg_template_id",
        ),
        sa.UniqueConstraint(
            "template_id",
            "sort_order",
            name="uq_spptdg_template_sort_order",
        ),
    )
    op.create_index(
        "ix_spptdg_template_id",
        "shipping_provider_pricing_template_destination_groups",
        ["template_id"],
        unique=False,
    )

    op.create_table(
        "shipping_provider_pricing_template_destination_group_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("province_code", sa.String(length=32), nullable=True),
        sa.Column("province_name", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["shipping_provider_pricing_template_destination_groups.id"],
            ondelete="CASCADE",
            name="fk_spptdgm_group_id",
        ),
        sa.CheckConstraint(
            "(province_name IS NOT NULL OR province_code IS NOT NULL)",
            name="ck_spptdgm_province_required",
        ),
    )
    op.create_index(
        "ix_spptdgm_group_province",
        "shipping_provider_pricing_template_destination_group_members",
        ["group_id", "province_code", "province_name"],
        unique=False,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_spptdgm_group_province_key
        ON shipping_provider_pricing_template_destination_group_members
        (group_id, COALESCE(province_code, ''), COALESCE(province_name, ''))
        """
    )

    op.create_table(
        "shipping_provider_pricing_template_matrix",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("pricing_mode", sa.String(length=32), nullable=False),
        sa.Column("flat_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("rate_per_kg", sa.Numeric(12, 4), nullable=True),
        sa.Column("base_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("module_range_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["shipping_provider_pricing_template_destination_groups.id"],
            ondelete="CASCADE",
            name="fk_spptm_group_id",
        ),
        sa.ForeignKeyConstraint(
            ["module_range_id"],
            ["shipping_provider_pricing_template_module_ranges.id"],
            ondelete="CASCADE",
            name="fk_spptm_module_range_id",
        ),
        sa.UniqueConstraint(
            "group_id",
            "module_range_id",
            name="uq_spptm_group_module_range",
        ),
    )
    op.create_index(
        "ix_spptm_group_id",
        "shipping_provider_pricing_template_matrix",
        ["group_id"],
        unique=False,
    )

    op.create_table(
        "shipping_provider_pricing_template_surcharge_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("province_code", sa.String(length=32), nullable=False),
        sa.Column("province_name", sa.String(length=64), nullable=True),
        sa.Column(
            "province_mode",
            sa.String(length=16),
            nullable=False,
            server_default="province",
        ),
        sa.Column(
            "fixed_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["shipping_provider_pricing_templates.id"],
            ondelete="CASCADE",
            name="fk_spptsc_template_id",
        ),
        sa.UniqueConstraint(
            "template_id",
            "province_code",
            name="uq_spptsc_template_province",
        ),
        sa.CheckConstraint(
            "province_mode in ('province','cities')",
            name="ck_spptsc_province_mode",
        ),
        sa.CheckConstraint(
            "fixed_amount >= 0",
            name="ck_spptsc_fixed_amount",
        ),
    )
    op.create_index(
        "ix_spptsc_template_active",
        "shipping_provider_pricing_template_surcharge_configs",
        ["template_id", "active"],
        unique=False,
    )

    op.create_table(
        "shipping_provider_pricing_template_surcharge_config_cities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("config_id", sa.Integer(), nullable=False),
        sa.Column("city_code", sa.String(length=32), nullable=False),
        sa.Column("city_name", sa.String(length=64), nullable=True),
        sa.Column(
            "fixed_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["config_id"],
            ["shipping_provider_pricing_template_surcharge_configs.id"],
            ondelete="CASCADE",
            name="fk_spptscc_config_id",
        ),
        sa.UniqueConstraint(
            "config_id",
            "city_code",
            name="uq_spptscc_city",
        ),
        sa.CheckConstraint(
            "fixed_amount >= 0",
            name="ck_spptscc_fixed_amount",
        ),
    )
    op.create_index(
        "ix_spptscc_config_active",
        "shipping_provider_pricing_template_surcharge_config_cities",
        ["config_id", "active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_spptscc_config_active",
        table_name="shipping_provider_pricing_template_surcharge_config_cities",
    )
    op.drop_table("shipping_provider_pricing_template_surcharge_config_cities")

    op.drop_index(
        "ix_spptsc_template_active",
        table_name="shipping_provider_pricing_template_surcharge_configs",
    )
    op.drop_table("shipping_provider_pricing_template_surcharge_configs")

    op.drop_index("ix_spptm_group_id", table_name="shipping_provider_pricing_template_matrix")
    op.drop_table("shipping_provider_pricing_template_matrix")

    op.execute("DROP INDEX IF EXISTS uq_spptdgm_group_province_key")
    op.drop_index(
        "ix_spptdgm_group_province",
        table_name="shipping_provider_pricing_template_destination_group_members",
    )
    op.drop_table("shipping_provider_pricing_template_destination_group_members")

    op.drop_index(
        "ix_spptdg_template_id",
        table_name="shipping_provider_pricing_template_destination_groups",
    )
    op.drop_table("shipping_provider_pricing_template_destination_groups")

    op.drop_index(
        "ix_spptmr_template_id",
        table_name="shipping_provider_pricing_template_module_ranges",
    )
    op.drop_table("shipping_provider_pricing_template_module_ranges")

    op.drop_table("shipping_provider_pricing_templates")
