"""items add brand category

Revision ID: 9dd9c977951c
Revises: c2eb15eb5915
Create Date: 2026-01-09 16:31:47.179272

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9dd9c977951c"
down_revision: Union[str, Sequence[str], None] = "c2eb15eb5915"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("items", sa.Column("brand", sa.String(length=64), nullable=True))
    op.add_column("items", sa.Column("category", sa.String(length=64), nullable=True))

    # 可选但推荐：列表页/筛选/聚合会用到，索引很值
    op.create_index("ix_items_brand", "items", ["brand"], unique=False)
    op.create_index("ix_items_category", "items", ["category"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_items_category", table_name="items")
    op.drop_index("ix_items_brand", table_name="items")

    op.drop_column("items", "category")
    op.drop_column("items", "brand")
