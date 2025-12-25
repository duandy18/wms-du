"""add_items_sku_seq

Revision ID: a8fa05588df5
Revises: 7b5b0d8f53e2
Create Date: 2025-12-13 03:17:01.543827
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8fa05588df5"
down_revision: Union[str, Sequence[str], None] = "7b5b0d8f53e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    创建商品 SKU 序列号：
    - 统一由后端生成 AKT-000001...
    - 使用 PostgreSQL sequence
    """
    op.execute(
        sa.text(
            """
            CREATE SEQUENCE IF NOT EXISTS items_sku_seq
            START WITH 1
            INCREMENT BY 1
            NO MINVALUE
            NO MAXVALUE
            CACHE 1
            """
        )
    )


def downgrade() -> None:
    """
    回滚：删除 SKU 序列号
    """
    op.execute(sa.text("DROP SEQUENCE IF EXISTS items_sku_seq"))
