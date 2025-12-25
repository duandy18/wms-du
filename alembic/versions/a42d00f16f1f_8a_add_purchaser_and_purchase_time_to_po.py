"""8a_add_purchaser_and_purchase_time_to_po

Revision ID: a42d00f16f1f
Revises: 2714e7999825
Create Date: 2025-12-11 21:52:59.336996
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a42d00f16f1f"
down_revision: Union[str, Sequence[str], None] = "2714e7999825"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add purchaser + purchase_time to purchase_orders."""

    # 1) 添加 purchaser（先给默认值，避免 NOT NULL 报错）
    op.add_column(
        "purchase_orders",
        sa.Column(
            "purchaser",
            sa.String(length=64),
            nullable=False,
            server_default="采购员",
        ),
    )

    # 2) 添加 purchase_time（先给默认值）
    op.add_column(
        "purchase_orders",
        sa.Column(
            "purchase_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # 3) 立刻移除默认值，恢复正常非空字段
    op.alter_column("purchase_orders", "purchaser", server_default=None)
    op.alter_column("purchase_orders", "purchase_time", server_default=None)


def downgrade() -> None:
    """Downgrade schema: drop purchaser + purchase_time."""

    op.drop_column("purchase_orders", "purchase_time")
    op.drop_column("purchase_orders", "purchaser")
