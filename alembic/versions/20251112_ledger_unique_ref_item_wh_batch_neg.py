"""enforce idempotency: unique (ref,item,wh,batch) for negative ledger

Revision ID: 20251112_ledger_unique_ref_item_wh_batch_neg
Revises: 20251112_batches_constraint_cleanup  # ← 按你的实际 head 调整
Create Date: 2025-11-12 15:10:00
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "20251112_ledger_unique_ref_item_wh_batch_neg"
down_revision: Union[str, Sequence[str], None] = "20251112_batches_constraint_cleanup"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1) 预清理：同一 (ref,item,wh,batch) 下的重复负向扣减，保留最早一条（最小 id）
    op.execute("""
    WITH dup AS (
      SELECT id,
             ROW_NUMBER() OVER (
               PARTITION BY ref, item_id, warehouse_id, batch_code
               ORDER BY id
             ) AS rn
      FROM stock_ledger
      WHERE delta < 0
    )
    DELETE FROM stock_ledger sl
    USING dup
    WHERE sl.id = dup.id
      AND dup.rn > 1;
    """)

    # 2) 建立部分唯一索引：只约束负向（出库）扣减
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_ref_item_wh_batch_neg
    ON stock_ledger (ref, item_id, warehouse_id, batch_code)
    WHERE (delta < 0)
    """)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_ledger_ref_item_wh_batch_neg")
