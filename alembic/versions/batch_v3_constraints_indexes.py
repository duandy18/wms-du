"""Batch v3 constraints and indexes (schema-aware, CI-safe)

Revision ID: batch_v3_constraints_indexes
Revises: f15351377fef
Create Date: 2025-11-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "batch_v3_constraints_indexes"
down_revision: Union[str, Sequence[str], None] = "f15351377fef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, col: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name   = :t
                   AND column_name  = :c
                 LIMIT 1
                """
            ),
            {"t": table, "c": col},
        ).first()
    )


def upgrade() -> None:
    """Upgrade schema.

    目标（原意）：
    - 为 batches 建立以 (warehouse_id, item_id, batch_code) 为键的索引/约束，优化 v3 批次查询。

    调整：
    - 仅当 batches.warehouse_id 存在时才建索引；
    - 在“无 warehouse_id 列”的库上，本迁移视为 NOOP，避免 UndefinedColumn。
    """
    bind = op.get_bind()

    if not _has_column(bind, "batches", "warehouse_id"):
        # 在 v2 纯 item+batch 字典模式下，warehouse_id 不存在，这里的索引就没有意义，直接跳过。
        return

    # 索引：按 (warehouse_id, item_id, batch_code) 提升批次查找性能
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_indexes
             WHERE schemaname = 'public'
               AND indexname  = 'ix_batches_wh_item_code'
          ) THEN
            CREATE INDEX ix_batches_wh_item_code
              ON batches (warehouse_id, item_id, batch_code);
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    """Downgrade schema.

    回滚时尽量把这条索引删掉（如果存在的话）。
    """
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_indexes
             WHERE schemaname = 'public'
               AND indexname  = 'ix_batches_wh_item_code'
          ) THEN
            DROP INDEX ix_batches_wh_item_code;
          END IF;
        END$$;
        """
    )
