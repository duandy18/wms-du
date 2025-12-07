"""
drop legacy stock_id column from stock_ledger

Revision ID: e21d07741545
Revises: f350ed5f47cf
Create Date: 2025-11-26 11:19:10.715840
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e21d07741545"
down_revision = "f350ed5f47cf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade schema:
    Remove legacy v1 column `stock_id` from stock_ledger.
    - 此列在 v1 架构用于指向 stocks.id
    - v2 架构完全基于 (warehouse_id, item_id, batch_code) 三元组
    - 所有幂等性约束已迁移至 v2 维度，不再需要 stock_id
    """
    op.drop_column("stock_ledger", "stock_id")


def downgrade() -> None:
    """
    Downgrade schema:
    Reintroduce `stock_id` as nullable integer.
    - 仅用于向下兼容，不再推荐使用。
    """
    op.add_column(
        "stock_ledger",
        sa.Column("stock_id", sa.Integer(), nullable=True),
    )
