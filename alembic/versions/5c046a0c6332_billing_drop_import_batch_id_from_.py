"""billing: drop import_batch_id from carrier_bill_items

Revision ID: 5c046a0c6332
Revises: ae85f671f02b
Create Date: 2026-03-18 13:25:36.527595
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c046a0c6332'
down_revision: Union[str, Sequence[str], None] = 'ae85f671f02b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 先删旧索引
    op.execute(
        """
        DROP INDEX IF EXISTS ix_carrier_bill_items_import_batch_id;
        """
    )

    # 2) 再删列
    op.drop_column("carrier_bill_items", "import_batch_id")


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 恢复列（仅恢复结构，不恢复历史数据）
    op.add_column(
        "carrier_bill_items",
        sa.Column(
            "import_batch_id",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )

    # 2) 恢复索引
    op.create_index(
        "ix_carrier_bill_items_import_batch_id",
        "carrier_bill_items",
        ["import_batch_id"],
        unique=False,
    )
