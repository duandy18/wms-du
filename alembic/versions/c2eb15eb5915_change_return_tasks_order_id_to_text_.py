"""change return_tasks.order_id to text order_ref

Revision ID: c2eb15eb5915
Revises: b11e8a98b164
Create Date: 2026-01-08 19:58:49.072384

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2eb15eb5915"
down_revision: Union[str, Sequence[str], None] = "b11e8a98b164"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # order_id: bigint -> varchar(128)
    op.alter_column(
        "return_tasks",
        "order_id",
        existing_type=sa.BigInteger(),
        type_=sa.String(length=128),
        nullable=False,
        postgresql_using="order_id::text",
    )

    op.execute(
        sa.text(
            "COMMENT ON COLUMN return_tasks.order_id IS "
            "'订单来源键（order_ref）：用于关联出库台账 stock_ledger.ref（字符串），必填'"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    # ⚠️ 只有在所有 order_id 都是纯数字字符串时才可降级成功，否则会失败
    op.alter_column(
        "return_tasks",
        "order_id",
        existing_type=sa.String(length=128),
        type_=sa.BigInteger(),
        nullable=False,
        postgresql_using="order_id::bigint",
    )

    op.execute(
        sa.text(
            "COMMENT ON COLUMN return_tasks.order_id IS "
            "'关联订单 orders.id（订单退货回仓任务来源，必填）'"
        )
    )
