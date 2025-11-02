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
    幂等：存在则先删；无则建；重复执行不报错。
    """
    conn = op.get_bind()
    conn.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
              -- 如果已存在同名唯一约束，先删除
              IF EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                 WHERE t.relname = '{TABLE}'
                   AND c.conname = '{UQ}'
                   AND c.contype = 'u'
              ) THEN
                ALTER TABLE {TABLE} DROP CONSTRAINT {UQ};
              END IF;

              -- 若当前不存在同名唯一约束，则以 DEFERRABLE 方式创建
              IF NOT EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                 WHERE t.relname = '{TABLE}'
                   AND c.conname = '{UQ}'
                   AND c.contype = 'u'
              ) THEN
                ALTER TABLE {TABLE}
                ADD CONSTRAINT {UQ}
                UNIQUE (reason, ref, ref_line, stock_id)
                DEFERRABLE INITIALLY DEFERRED;
              END IF;
            END$$;
            """
        )
    )


def downgrade() -> None:
    """
    回滚：如果存在 DEFERRABLE 版本，则删除；再创建非 DEFERRABLE 的普通唯一约束，
    以匹配旧版数据库形态。
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
                ALTER TABLE {TABLE} DROP CONSTRAINT {UQ};
              END IF;
            END$$;
            """
        )
    )

    # 旧形态（非 deferrable）
    op.create_unique_constraint(UQ, TABLE, ["reason", "ref", "ref_line", "stock_id"])
