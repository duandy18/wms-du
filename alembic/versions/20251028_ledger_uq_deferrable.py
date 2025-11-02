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
    # 1) 若已存在同名约束，先删（避免重复），再以 DEFERRABLE 方式重建
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                 WHERE t.relname = :tbl
                   AND c.conname = :cname
                   AND c.contype = 'u'
              ) THEN
                ALTER TABLE {TABLE} DROP CONSTRAINT {UQ};
              END IF;

              -- 以 DEFERRABLE INITIALLY DEFERRED 方式创建（若此前没有或刚删除）
              IF NOT EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                 WHERE t.relname = :tbl
                   AND c.conname = :cname
                   AND c.contype = 'u'
              ) THEN
                ALTER TABLE {TABLE}
                ADD CONSTRAINT {UQ}
                UNIQUE (reason, ref, ref_line, stock_id) DEFERRABLE INITIALLY DEFERRED;
              END IF;
            END$$;
            """
        ),
        {"tbl": TABLE, "cname": UQ},
    )


def downgrade() -> None:
    # 回滚：若存在则删除，再以非 DEFERRABLE 的普通唯一约束重建
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                 WHERE t.relname = :tbl
                   AND c.conname = :cname
                   AND c.contype = 'u'
              ) THEN
                ALTER TABLE {TABLE} DROP CONSTRAINT {UQ};
              END IF;
            END$$;
            """
        ),
        {"tbl": TABLE, "cname": UQ},
    )

    # 非 deferrable 的普通唯一（保持与历史降级一致）
    op.create_unique_constraint(UQ, TABLE, ["reason", "ref", "ref_line", "stock_id"])
