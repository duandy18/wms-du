"""add warehouse_service_cities (route-c city mapping)

Revision ID: bf1cdd998bda
Revises: 641f17c4aee9
Create Date: 2026-01-18 18:32:45.761273

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bf1cdd998bda"
down_revision: Union[str, Sequence[str], None] = "641f17c4aee9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warehouse_service_cities",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("province_code", sa.String(length=32), nullable=True),
        sa.Column("city_code", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_wh_service_cities_warehouse",
            ondelete="RESTRICT",
        ),
    )

    # city 全局互斥：同一个 city 只能属于一个仓
    op.create_index(
        "ux_wh_service_cities_city_code",
        "warehouse_service_cities",
        ["city_code"],
        unique=True,
    )

    # 方便按仓查询
    op.create_index(
        "ix_wh_service_cities_warehouse_id",
        "warehouse_service_cities",
        ["warehouse_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_wh_service_cities_warehouse_id", table_name="warehouse_service_cities")
    op.drop_index("ux_wh_service_cities_city_code", table_name="warehouse_service_cities")
    op.drop_table("warehouse_service_cities")
