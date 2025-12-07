"""batches: drop legacy date columns (production_date/expiry_date/shelf_life_days)

Revision ID: 20251110_batches_drop_legacy_dates
Revises: 20251110_event_log_drop_old_idx
Create Date: 2025-11-09 13:21:30
"""

from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251110_batches_drop_legacy_dates"
down_revision: Union[str, Sequence[str], None] = "20251110_event_log_drop_old_idx"
branch_labels = None
depends_on = None


UPGRADE_FEFO_VIEW = """
-- 以 expire_at 为基准的 FEFO 视图（通用最小定义；如需更复杂逻辑，后续可替换）
CREATE VIEW v_fefo_rank AS
SELECT
  b.id            AS batch_id,
  b.item_id       AS item_id,
  b.warehouse_id  AS warehouse_id,
  b.location_id   AS location_id,
  b.expire_at     AS expire_at
FROM batches b
WHERE b.expire_at IS NOT NULL
ORDER BY b.expire_at ASC, b.id ASC;
"""

DOWNGRADE_FEFO_VIEW = """
-- 使用 legacy 列 expiry_date 的 FEFO 视图（回滚用的保守定义）
CREATE VIEW v_fefo_rank AS
SELECT
  b.id            AS batch_id,
  b.item_id       AS item_id,
  b.warehouse_id  AS warehouse_id,
  b.location_id   AS location_id,
  b.expiry_date   AS expiry_date
FROM batches b
WHERE b.expiry_date IS NOT NULL
ORDER BY b.expiry_date ASC, b.id ASC;
"""


def upgrade() -> None:
    # 1) 显式删除依赖视图，避免 DROP COLUMN 被阻塞
    op.execute("DROP VIEW IF EXISTS v_fefo_rank;")

    # 2) 删除 legacy 列（幂等）
    op.execute(
        """
        ALTER TABLE batches
          DROP COLUMN IF EXISTS production_date,
          DROP COLUMN IF EXISTS expiry_date,
          DROP COLUMN IF EXISTS shelf_life_days;
        """
    )

    # 3) 重建基于 expire_at 的 v_fefo_rank（保持 FEFO 能力）
    op.execute(UPGRADE_FEFO_VIEW)


def downgrade() -> None:
    # 回滚：用旧列定义恢复视图，再把列加回（顺序相反）
    op.execute("DROP VIEW IF EXISTS v_fefo_rank;")

    op.execute(
        """
        ALTER TABLE batches
          ADD COLUMN IF NOT EXISTS production_date DATE,
          ADD COLUMN IF NOT EXISTS expiry_date DATE,
          ADD COLUMN IF NOT EXISTS shelf_life_days INTEGER;
        """
    )

    op.execute(DOWNGRADE_FEFO_VIEW)
