"""store_province_routes

Revision ID: 7e2f4ccfef3b
Revises: 1bd3771db4fc
Create Date: 2026-01-16 14:27:12.247999

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7e2f4ccfef3b"
down_revision: Union[str, Sequence[str], None] = "1bd3771db4fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_province_routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("province", sa.String(length=32), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
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
            ["store_id"],
            ["stores.id"],
            name="fk_store_province_routes_store",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_store_province_routes_wh",
        ),
    )

    # 同一个店铺、同一个省：priority 必须唯一
    op.create_index(
        "ix_store_province_routes_store_province_priority",
        "store_province_routes",
        ["store_id", "province", "priority"],
        unique=True,
    )

    # 常用查询：按店铺 + 省取候选仓
    op.create_index(
        "ix_store_province_routes_store_province",
        "store_province_routes",
        ["store_id", "province"],
        unique=False,
    )

    # 常用查询：按店铺取所有规则
    op.create_index(
        "ix_store_province_routes_store",
        "store_province_routes",
        ["store_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_store_province_routes_store", table_name="store_province_routes")
    op.drop_index(
        "ix_store_province_routes_store_province",
        table_name="store_province_routes",
    )
    op.drop_index(
        "ix_store_province_routes_store_province_priority",
        table_name="store_province_routes",
    )
    op.drop_table("store_province_routes")
