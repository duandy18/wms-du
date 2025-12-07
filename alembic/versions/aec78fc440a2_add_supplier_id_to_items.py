"""add supplier_id to items

Revision ID: aec78fc440a2
Revises: 8ca4bc063929
Create Date: 2025-11-28 19:30:00.740879
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aec78fc440a2"
down_revision: Union[str, Sequence[str], None] = "8ca4bc063929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add supplier_id to items"""

    # 1) 新增 supplier_id 列
    op.add_column(
        "items",
        sa.Column("supplier_id", sa.Integer(), nullable=True),
    )

    # 2) 为 supplier_id 建索引
    op.create_index(
        "ix_items_supplier_id",
        "items",
        ["supplier_id"],
        unique=False,
    )

    # 3) 建立外键 → suppliers.id
    op.create_foreign_key(
        "fk_items_supplier",
        "items",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema: drop supplier_id"""

    # 删除外键
    op.drop_constraint("fk_items_supplier", "items", type_="foreignkey")

    # 删除索引
    op.drop_index("ix_items_supplier_id", table_name="items")

    # 删除列
    op.drop_column("items", "supplier_id")
