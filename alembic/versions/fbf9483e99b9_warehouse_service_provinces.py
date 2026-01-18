"""warehouse service provinces

Revision ID: fbf9483e99b9
Revises: 150d827e9834
Create Date: 2026-01-17 17:03:49.888642
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fbf9483e99b9"
down_revision: Union[str, Sequence[str], None] = "150d827e9834"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "warehouse_service_provinces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("province_code", sa.String(length=64), nullable=False),
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
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            ondelete="CASCADE",
        ),
    )

    # 常用查询索引
    op.create_index(
        "ix_wh_service_provinces_warehouse_id",
        "warehouse_service_provinces",
        ["warehouse_id"],
    )

    # 🔒 路线 C 的核心约束：省份全局唯一
    op.create_unique_constraint(
        "uq_wh_service_province_code",
        "warehouse_service_provinces",
        ["province_code"],
    )

    # 同一仓内不允许重复配置同一省（防御性约束）
    op.create_unique_constraint(
        "uq_wh_service_province_wh_code",
        "warehouse_service_provinces",
        ["warehouse_id", "province_code"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_wh_service_province_wh_code",
        "warehouse_service_provinces",
        type_="unique",
    )
    op.drop_constraint(
        "uq_wh_service_province_code",
        "warehouse_service_provinces",
        type_="unique",
    )
    op.drop_index(
        "ix_wh_service_provinces_warehouse_id",
        table_name="warehouse_service_provinces",
    )
    op.drop_table("warehouse_service_provinces")
