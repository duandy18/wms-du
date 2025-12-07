"""outbound_commits: add unique guard (CI-safe, idempotent)

Revision ID: u1_outbound_commits_unique
Revises: e1e0g01
Create Date: 2024-10-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision = "u1_outbound_commits_unique"
down_revision = "e1e0g01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    在 CI / 本地差异环境下安全地为 outbound_commits 添加唯一约束/索引。
    兼容两种历史结构：
      A) 唯一键为 (shop_id, ref)
      B) 唯一键仅为 (ref)
    若表或列不存在则不做任何操作（幂等）。
    """
    conn = op.get_bind()

    # 先删可能遗留的历史索引/唯一索引（名称不定，全部用 IF EXISTS 兜底）
    conn.execute(
        sa.text("""
    DO $$
    BEGIN
      IF to_regclass('public.outbound_commits') IS NULL THEN
        RETURN; -- 表不存在，直接跳过
      END IF;

      -- 老名字兜底（存在就删，不存在就跳过）
      BEGIN EXECUTE 'DROP INDEX IF EXISTS public.ix_outbound_commits_ref'; EXCEPTION WHEN OTHERS THEN END;
      BEGIN EXECUTE 'DROP INDEX IF EXISTS public.uq_outbound_ref_item_loc'; EXCEPTION WHEN OTHERS THEN END;
      BEGIN EXECUTE 'ALTER TABLE public.outbound_commits DROP CONSTRAINT IF EXISTS uq_outbound_commits_shop_ref'; EXCEPTION WHEN OTHERS THEN END;
      BEGIN EXECUTE 'ALTER TABLE public.outbound_commits DROP CONSTRAINT IF EXISTS uq_outbound_commits_ref'; EXCEPTION WHEN OTHERS THEN END;

      -- 根据列存在性选择唯一键方案
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='shop_id'
      ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='ref'
      ) THEN
        -- 方案 A： (shop_id, ref) 唯一
        IF NOT EXISTS (
          SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid
           WHERE t.relname='outbound_commits' AND c.conname='uq_outbound_commits_shop_ref' AND c.contype='u'
        ) THEN
          EXECUTE 'ALTER TABLE public.outbound_commits
                     ADD CONSTRAINT uq_outbound_commits_shop_ref
                     UNIQUE (shop_id, ref)';
        END IF;
      ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='ref'
      ) THEN
        -- 方案 B：仅 ref 唯一（历史结构）
        IF NOT EXISTS (
          SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid
           WHERE t.relname='outbound_commits' AND c.conname='uq_outbound_commits_ref' AND c.contype='u'
        ) THEN
          EXECUTE 'ALTER TABLE public.outbound_commits
                     ADD CONSTRAINT uq_outbound_commits_ref
                     UNIQUE (ref)';
        END IF;
      END IF;
    END $$;
    """)
    )


def downgrade() -> None:
    """
    回滚仅做“安全删除唯一约束/索引”（若存在），不再假设任何结构。
    """
    conn = op.get_bind()
    conn.execute(
        sa.text("""
    DO $$
    BEGIN
      IF to_regclass('public.outbound_commits') IS NULL THEN
        RETURN;
      END IF;

      -- 优先删约束（Postgres 唯一约束会有依赖索引，删约束即可）
      BEGIN EXECUTE 'ALTER TABLE public.outbound_commits DROP CONSTRAINT IF EXISTS uq_outbound_commits_shop_ref'; EXCEPTION WHEN OTHERS THEN END;
      BEGIN EXECUTE 'ALTER TABLE public.outbound_commits DROP CONSTRAINT IF EXISTS uq_outbound_commits_ref'; EXCEPTION WHEN OTHERS THEN END;

      -- 兜底：有些历史版本用 UNIQUE INDEX 名称而非约束名
      BEGIN EXECUTE 'DROP INDEX IF EXISTS public.uq_outbound_commits_shop_ref'; EXCEPTION WHEN OTHERS THEN END;
      BEGIN EXECUTE 'DROP INDEX IF EXISTS public.uq_outbound_commits_ref'; EXCEPTION WHEN OTHERS THEN END;
      BEGIN EXECUTE 'DROP INDEX IF EXISTS public.ix_outbound_commits_ref'; EXCEPTION WHEN OTHERS THEN END;
      BEGIN EXECUTE 'DROP INDEX IF EXISTS public.uq_outbound_ref_item_loc'; EXCEPTION WHEN OTHERS THEN END;
    END $$;
    """)
    )
