"""phase_3_7_drop_reservations_legacy_index

Revision ID: 7b4bd5845884
Revises: 91e6bfcca3b0
Create Date: 2025-11-16 12:21:28.703569
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "7b4bd5845884"
down_revision: Union[str, Sequence[str], None] = "91e6bfcca3b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy partial unique index uq_reservations_platform_shop_ref, if present.

    旧索引：
      - 名称：uq_reservations_platform_shop_ref
      - 形式：UNIQUE (platform, shop_id, ref)
              WHERE platform IS NOT NULL AND shop_id IS NOT NULL

    该索引与新的四维唯一约束 (platform, shop_id, warehouse_id, ref) 冲突，
    会导致 INSERT ... ON CONFLICT(...) 并发场景下命中错误的唯一键。
    """
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS uq_reservations_platform_shop_ref
            """
        )
    )


def downgrade() -> None:
    """Recreate legacy 3D unique partial index (仅回滚时使用)."""
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_platform_shop_ref
            ON reservations (platform, shop_id, ref)
            WHERE platform IS NOT NULL AND shop_id IS NOT NULL
            """
        )
    )
