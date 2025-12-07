"""add_warehouse_contact_fields

Revision ID: 8230735fe423
Revises: 63a608f5cbe1
Create Date: 2025-11-27 08:51:58.925140
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8230735fe423"
down_revision: Union[str, Sequence[str], None] = "63a608f5cbe1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    给 warehouses 表新增扩展字段：
    - address: 仓库地址，可选
    - contact_name: 联系人姓名，可选
    - contact_phone: 联系电话，可选
    - area_sqm: 仓库面积（整数，单位 m²），可选
    """

    op.add_column(
        "warehouses",
        sa.Column("address", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "warehouses",
        sa.Column("contact_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "warehouses",
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "warehouses",
        sa.Column("area_sqm", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """
    回滚上述字段。
    """

    op.drop_column("warehouses", "area_sqm")
    op.drop_column("warehouses", "contact_phone")
    op.drop_column("warehouses", "contact_name")
    op.drop_column("warehouses", "address")
