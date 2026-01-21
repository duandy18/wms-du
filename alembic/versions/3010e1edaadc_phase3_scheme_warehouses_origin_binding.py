"""phase3: scheme warehouses origin binding

Revision ID: 3010e1edaadc
Revises: 460104059fbd
Create Date: 2026-01-21 11:43:31.763402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3010e1edaadc"
down_revision: Union[str, Sequence[str], None] = "460104059fbd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shipping_provider_pricing_scheme_warehouses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["shipping_provider_pricing_schemes.id"],
            name="fk_sp_scheme_wh_scheme_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_sp_scheme_wh_warehouse_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("scheme_id", "warehouse_id", name="uq_sp_scheme_wh_scheme_warehouse"),
    )

    op.create_index(
        "ix_sp_scheme_wh_warehouse_id",
        "shipping_provider_pricing_scheme_warehouses",
        ["warehouse_id"],
    )
    op.create_index(
        "ix_sp_scheme_wh_scheme_id",
        "shipping_provider_pricing_scheme_warehouses",
        ["scheme_id"],
    )
    op.create_index(
        "ix_sp_scheme_wh_active",
        "shipping_provider_pricing_scheme_warehouses",
        ["active"],
    )


def downgrade() -> None:
    op.drop_index("ix_sp_scheme_wh_active", table_name="shipping_provider_pricing_scheme_warehouses")
    op.drop_index("ix_sp_scheme_wh_scheme_id", table_name="shipping_provider_pricing_scheme_warehouses")
    op.drop_index("ix_sp_scheme_wh_warehouse_id", table_name="shipping_provider_pricing_scheme_warehouses")
    op.drop_table("shipping_provider_pricing_scheme_warehouses")
