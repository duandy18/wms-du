"""phase_3_7_drop_legacy_reservations_unique

Revision ID: 91e6bfcca3b0
Revises: 514b4b687a19
Create Date: 2025-11-16 12:04:12.475082
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "91e6bfcca3b0"
down_revision: Union[str, Sequence[str], None] = "514b4b687a19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy 3D unique (constraint or index) on reservations, if present.

    旧设计：
      - 通过 uq_reservations_platform_shop_ref 做三维唯一：
          (platform, shop_id, ref) [带 WHERE platform IS NOT NULL AND shop_id IS NOT NULL]
      - 实际上它是一个 partial unique index，而不是表级 constraint。

    新设计：
      - 只保留四维唯一：
          uq_reservations_platform_shop_wh_ref(platform, shop_id, warehouse_id, ref)

    为了让 ON CONFLICT (platform, shop_id, warehouse_id, ref) 在并发场景下正常工作，
    必须删除旧的三维唯一索引，否则 PG 会优先命中 uq_reservations_platform_shop_ref。
    """
    # 1) 以防某些环境曾经用过 constraint 形式：先尝试 drop constraint
    op.execute(
        sa.text(
            """
            ALTER TABLE reservations
            DROP CONSTRAINT IF EXISTS uq_reservations_platform_shop_ref
            """
        )
    )

    # 2) 正常情况是 partial unique index，这里显式删除索引本身
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS uq_reservations_platform_shop_ref
            """
        )
    )


def downgrade() -> None:
    """Recreate legacy 3D unique index (partial), 若需要回滚时用。

    注意：这里恢复的是原先的 partial unique index 形式，
    而不是表级 constraint。
    """
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_platform_shop_ref
            ON reservations (platform, shop_id, ref)
            WHERE platform IS NOT NULL AND shop_id IS NOT NULL
            """
        )
    )
