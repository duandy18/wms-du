"""add_shipping_provider_surcharge_configs

Revision ID: 70f2fe66a679
Revises: 4f4a1115b080
Create Date: 2026-03-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "70f2fe66a679"
down_revision: Union[str, Sequence[str], None] = "4f4a1115b080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===============================
    # province surcharge config
    # ===============================

    op.create_table(
        "shipping_provider_surcharge_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "scheme_id",
            sa.Integer(),
            sa.ForeignKey(
                "shipping_provider_pricing_schemes.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "province_code",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "province_name",
            sa.String(64),
            nullable=True,
        ),
        # province = 全省收费
        # cities   = 仅指定城市收费，省内其他城市不收费
        sa.Column(
            "province_mode",
            sa.String(16),
            nullable=False,
            server_default="province",
        ),
        # 仅 province_mode=province 时使用
        sa.Column(
            "fixed_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        sa.UniqueConstraint(
            "scheme_id",
            "province_code",
            name="uq_sp_surcharge_configs_scheme_province_code",
        ),
        sa.CheckConstraint(
            "province_mode in ('province','cities')",
            name="ck_sp_surcharge_configs_province_mode_valid",
        ),
        sa.CheckConstraint(
            "fixed_amount >= 0",
            name="ck_sp_surcharge_configs_fixed_amount_non_negative",
        ),
    )

    op.create_index(
        "ix_sp_surcharge_configs_scheme_active",
        "shipping_provider_surcharge_configs",
        ["scheme_id", "active"],
    )

    # ===============================
    # city surcharge rules
    # ===============================

    op.create_table(
        "shipping_provider_surcharge_config_cities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "config_id",
            sa.Integer(),
            sa.ForeignKey(
                "shipping_provider_surcharge_configs.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "city_code",
            sa.String(32),
            nullable=False,
        ),
        sa.Column(
            "city_name",
            sa.String(64),
            nullable=True,
        ),
        sa.Column(
            "fixed_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
        sa.UniqueConstraint(
            "config_id",
            "city_code",
            name="uq_sp_surcharge_config_cities_config_city_code",
        ),
        sa.CheckConstraint(
            "fixed_amount >= 0",
            name="ck_sp_surcharge_config_cities_fixed_amount_non_negative",
        ),
    )

    op.create_index(
        "ix_sp_surcharge_config_cities_config_active",
        "shipping_provider_surcharge_config_cities",
        ["config_id", "active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sp_surcharge_config_cities_config_active",
        table_name="shipping_provider_surcharge_config_cities",
    )

    op.drop_table("shipping_provider_surcharge_config_cities")

    op.drop_index(
        "ix_sp_surcharge_configs_scheme_active",
        table_name="shipping_provider_surcharge_configs",
    )

    op.drop_table("shipping_provider_surcharge_configs")
