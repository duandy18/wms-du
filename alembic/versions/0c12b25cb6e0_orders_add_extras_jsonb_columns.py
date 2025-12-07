"""orders+: add extras jsonb columns

Revision ID: 0c12b25cb6e0
Revises: 5a61ee228b31
Create Date: 2025-11-07 15:43:47.226540
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0c12b25cb6e0"
down_revision: Union[str, Sequence[str], None] = "5a61ee228b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # orders.extras
    bind.execute(
        sa.text(
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS extras JSONB NOT NULL DEFAULT '{}'::jsonb"
        )
    )

    # order_items.extras
    # 注意：老表可能不存在；若不存在直接跳过（由上一条迁移负责创建）
    insp = sa.inspect(bind)
    if insp.has_table("order_items", schema="public"):
        bind.execute(
            sa.text(
                "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS extras JSONB NOT NULL DEFAULT '{}'::jsonb"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    # 回滚时保守处理：存在才删除
    bind.execute(sa.text("ALTER TABLE IF EXISTS order_items DROP COLUMN IF EXISTS extras"))
    bind.execute(sa.text("ALTER TABLE IF EXISTS orders DROP COLUMN IF EXISTS extras"))
