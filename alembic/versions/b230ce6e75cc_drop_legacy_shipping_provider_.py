"""drop legacy shipping_provider_surcharges table

Revision ID: b230ce6e75cc
Revises: 70f2fe66a679
Create Date: 2026-03-10 14:43:39.645082
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b230ce6e75cc"
down_revision: Union[str, Sequence[str], None] = "70f2fe66a679"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    删除旧附加费表 shipping_provider_surcharges。

    该表属于旧扁平 surcharge 架构，已被
    shipping_provider_surcharge_configs +
    shipping_provider_surcharge_config_cities
    新结构完全替代。

    代码侧与测试侧已完成迁移，数据库不再依赖该表。
    """

    # 直接删除旧表（索引/约束会自动一起删除）
    op.drop_table("shipping_provider_surcharges")


def downgrade() -> None:
    """
    恢复旧表结构（仅恢复结构，不恢复历史数据）。
    """

    op.create_table(
        "shipping_provider_surcharges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("province_code", sa.String(length=32), nullable=True),
        sa.Column("city_code", sa.String(length=32), nullable=True),
        sa.Column("province_name", sa.String(length=64), nullable=True),
        sa.Column("city_name", sa.String(length=64), nullable=True),
        sa.Column("fixed_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "province_mode",
            sa.String(length=16),
            nullable=False,
            server_default="province",
        ),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            name="fk_sp_surcharges_scheme_id",
            ondelete="RESTRICT",
        ),
    )

    # 原有索引
    op.create_index(
        "ix_sp_surcharges_scheme_active",
        "shipping_provider_surcharges",
        ["scheme_id", "active"],
    )

    # 唯一约束（province）
    op.create_index(
        "uq_sp_surcharges_active_province_key",
        "shipping_provider_surcharges",
        [
            "scheme_id",
            sa.text("COALESCE(province_code, '')"),
            sa.text("COALESCE(province_name, '')"),
        ],
        unique=True,
        postgresql_where=sa.text("active IS TRUE AND scope = 'province'"),
    )

    # 唯一约束（city）
    op.create_index(
        "uq_sp_surcharges_active_city_key",
        "shipping_provider_surcharges",
        [
            "scheme_id",
            sa.text("COALESCE(province_code, '')"),
            sa.text("COALESCE(province_name, '')"),
            sa.text("COALESCE(city_code, '')"),
            sa.text("COALESCE(city_name, '')"),
        ],
        unique=True,
        postgresql_where=sa.text("active IS TRUE AND scope = 'city'"),
    )

    # scheme+name 唯一约束
    op.create_unique_constraint(
        "uq_sp_surcharges_scheme_name",
        "shipping_provider_surcharges",
        ["scheme_id", "name"],
    )
