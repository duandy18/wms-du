"""shipping_provider_pricing_schemes_v1

Revision ID: eb0977f2d5e7
Revises: d0a758bd99ab
Create Date: 2025-12-13 17:32:46.645506
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "eb0977f2d5e7"
down_revision: Union[str, Sequence[str], None] = "d0a758bd99ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================
    # 1) pricing schemes（一个 provider 多套价：生效期/客户/优先级）
    # =========================================================
    op.create_table(
        "shipping_provider_pricing_schemes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("shipping_provider_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billable_weight_rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["shipping_provider_id"],
            ["shipping_providers.id"],
            name="fk_sp_pricing_schemes_provider_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_sp_pricing_schemes_provider_active",
        "shipping_provider_pricing_schemes",
        ["shipping_provider_id", "active"],
    )
    op.create_index(
        "ix_sp_pricing_schemes_provider_priority",
        "shipping_provider_pricing_schemes",
        ["shipping_provider_id", "priority"],
    )

    # =========================================================
    # 2) zones（目的地分区）
    # =========================================================
    op.create_table(
        "shipping_provider_zones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            name="fk_sp_zones_scheme_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("scheme_id", "name", name="uq_sp_zones_scheme_name"),
    )
    op.create_index("ix_sp_zones_scheme", "shipping_provider_zones", ["scheme_id"])
    op.create_index("ix_sp_zones_scheme_priority", "shipping_provider_zones", ["scheme_id", "priority"])

    # =========================================================
    # 3) zone members（zone 的成员：省/市/区/文本匹配）
    # =========================================================
    op.create_table(
        "shipping_provider_zone_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("zone_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),  # province/city/district/text
        sa.Column("value", sa.String(length=64), nullable=False),  # name or code
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["zone_id"],
            ["shipping_provider_zones.id"],
            name="fk_sp_zone_members_zone_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("zone_id", "level", "value", name="uq_sp_zone_members_zone_level_value"),
    )
    op.create_index(
        "ix_sp_zone_members_zone_level",
        "shipping_provider_zone_members",
        ["zone_id", "level"],
    )

    # =========================================================
    # 4) zone brackets（重量段 → 价格表达式）
    # =========================================================
    op.create_table(
        "shipping_provider_zone_brackets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("zone_id", sa.Integer(), nullable=False),
        sa.Column("min_kg", sa.Numeric(10, 3), nullable=False),
        sa.Column("max_kg", sa.Numeric(10, 3), nullable=True),  # null = infinity
        sa.Column("pricing_kind", sa.String(length=32), nullable=False),  # flat/step/per_kg/manual_quote
        sa.Column("price_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["zone_id"],
            ["shipping_provider_zones.id"],
            name="fk_sp_zone_brackets_zone_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_sp_zone_brackets_zone", "shipping_provider_zone_brackets", ["zone_id"])
    op.create_index("ix_sp_zone_brackets_range", "shipping_provider_zone_brackets", ["zone_id", "min_kg"])

    # =========================================================
    # 5) surcharges（附加费：条件 + 金额表达式）
    # =========================================================
    op.create_table(
        "shipping_provider_surcharges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("condition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("amount_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            name="fk_sp_surcharges_scheme_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("scheme_id", "name", name="uq_sp_surcharges_scheme_name"),
    )
    op.create_index("ix_sp_surcharges_scheme_active", "shipping_provider_surcharges", ["scheme_id", "active"])
    op.create_index("ix_sp_surcharges_scheme_priority", "shipping_provider_surcharges", ["scheme_id", "priority"])


def downgrade() -> None:
    op.drop_index("ix_sp_surcharges_scheme_priority", table_name="shipping_provider_surcharges")
    op.drop_index("ix_sp_surcharges_scheme_active", table_name="shipping_provider_surcharges")
    op.drop_table("shipping_provider_surcharges")

    op.drop_index("ix_sp_zone_brackets_range", table_name="shipping_provider_zone_brackets")
    op.drop_index("ix_sp_zone_brackets_zone", table_name="shipping_provider_zone_brackets")
    op.drop_table("shipping_provider_zone_brackets")

    op.drop_index("ix_sp_zone_members_zone_level", table_name="shipping_provider_zone_members")
    op.drop_table("shipping_provider_zone_members")

    op.drop_index("ix_sp_zones_scheme_priority", table_name="shipping_provider_zones")
    op.drop_index("ix_sp_zones_scheme", table_name="shipping_provider_zones")
    op.drop_table("shipping_provider_zones")

    op.drop_index("ix_sp_pricing_schemes_provider_priority", table_name="shipping_provider_pricing_schemes")
    op.drop_index("ix_sp_pricing_schemes_provider_active", table_name="shipping_provider_pricing_schemes")
    op.drop_table("shipping_provider_pricing_schemes")
