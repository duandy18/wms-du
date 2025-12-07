"""orders: drop legacy columns

Revision ID: 20251110_orders_drop_legacy
Revises: 20251110_batches_add_mfg_and_lot
Create Date: 2025-11-09 12:50:54.513636
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251110_orders_drop_legacy"
down_revision: Union[str, Sequence[str], None] = "20251110_batches_add_mfg_and_lot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: drop legacy columns on orders (idempotent)."""
    # 统一放在一个 ALTER TABLE 里；IF EXISTS 保证幂等
    op.execute(
        """
        ALTER TABLE orders
            DROP COLUMN IF EXISTS ext_order_no,
            DROP COLUMN IF EXISTS platform,
            DROP COLUMN IF EXISTS client_ref,
            DROP COLUMN IF EXISTS extras,
            DROP COLUMN IF EXISTS shop_id;
        """
    )


def downgrade() -> None:
    """Downgrade schema: restore columns with conservative (nullable) definitions."""
    # 回滚时按保守策略恢复列（nullable, 无默认值）；如需严格约束可在后续业务迁移里补
    # types 基于历史 DDL / diff：ext_order_no/shop_id(128), platform(32), client_ref(TEXT), extras(JSONB)
    op.execute(
        """
        ALTER TABLE orders
            ADD COLUMN IF NOT EXISTS ext_order_no VARCHAR(128),
            ADD COLUMN IF NOT EXISTS platform     VARCHAR(32),
            ADD COLUMN IF NOT EXISTS client_ref   TEXT,
            ADD COLUMN IF NOT EXISTS extras       JSONB,
            ADD COLUMN IF NOT EXISTS shop_id      VARCHAR(128);
        """
    )
