"""make ledger UQ deferrable initially deferred

Revision ID: 20251028_ledger_uq_deferrable
Revises: 20251028_batches_add_foreign_keys
Create Date: 2025-10-28 12:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20251028_ledger_uq_deferrable"
down_revision = "20251028_batches_add_foreign_keys"
branch_labels = None
depends_on = None

TABLE = "stock_ledger"
UQ = "uq_ledger_reason_ref_refline_stock"


def upgrade() -> None:
    """
    目标形态：
      CONSTRAINT uq_ledger_reason_ref_refline_stock
      UNIQUE (reason, ref, ref_line, stock_id) DEFERRABLE INITIALLY DEFERRED
    幂等策略：
      1) 若存在同名约束，先删
      2) 若存在同名索引，先删（历史可能先建了 index）
      3) 不存在时再添加 DEFERRABLE UQ
    """
    conn = op.get_bind()
    conn.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
              -- 1) 先删同名唯一约束（如果存在）
              IF EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                 WHERE t.relname = '{TABLE}'
                   AND c.conname = '{UQ}'
                   AND c.contype = 'u'
              ) THEN
                EXECUTE 'ALTER TABLE {TABLE} DROP CONSTRAINT {UQ}';
              END IF;

              -- 2) 再删同名索引（如果存在）
              --    注意：唯一约束会创建同名索引；若历史只建了索引也会占用名字
              IF EXISTS (
                SELECT 1
                  FROM pg_class
                 WHERE relname = '{UQ}'
                   AND relkind = 'i'  -- index
              ) THEN
                EXECUTE format('DROP INDEX %I', '{UQ}');
              END IF;

              -- 3) 若当前仍不存在唯一约束，则以 DEFERRABLE 方式创建
              IF NOT EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                 WHERE t.relname = '{TABLE}'
                   AND c.conname = '{UQ}'
                   AND c.contype = 'u'
              ) THEN
                EXECUTE '
                  ALTER TABLE {TABLE}
                  ADD CONSTRAINT {UQ}
                  UNIQUE (reason, ref, ref_line, stock_id)
                  DEFERRABLE INITIALLY DEFERRED
                ';
              END IF;
            END$$;
            """
        )
    )


def downgrade() -> None:
    """
    回滚：删掉 DEFERRABLE 唯一约束；然后重建非 DEFERRABLE 的普通唯一约束。
    """
    conn = op.get_bind()
    conn.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                 WHERE t.relname = '{TABLE}'
                   AND c.conname = '{UQ}'
                   AND c.contype = 'u'
              ) THEN
                EXECUTE 'ALTER TABLE {TABLE} DROP CONSTRAINT {UQ}';
              END IF;
              -- 若历史只留下了同名索引，顺手清理
              IF EXISTS (
                SELECT 1 FROM pg_class WHERE relname = '{UQ}' AND relkind = 'i'
              ) THEN
                EXECUTE format('DROP INDEX %I', '{UQ}');
              END IF;
            END$$;
            """
        )
    )

    # 旧形态（非 deferrable）
    op.create_unique_constraint(UQ, TABLE, ["reason", "ref", "ref_line", "stock_id"])
