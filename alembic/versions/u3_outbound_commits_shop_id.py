"""outbound_commits: add shop_id (guarded) + create 4-col unique index with platform

Revision ID: u3_outbound_commits_shop_id
Revises: u2_event_error_log_message_text
Create Date: 2025-10-xx
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# ---- Alembic identifiers ----
revision = "u3_outbound_commits_shop_id"
down_revision = "u2_event_error_log_message_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 列守卫：缺哪个补哪个（NOT NULL 先临时 DEFAULT，再移除 DEFAULT）
    # platform：字符串小枚举足够，历史上常用 'PDD' 等，给 16~32 足量
    conn.execute(sa.text("""
    DO $$
    BEGIN
      -- platform
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='platform'
      ) THEN
        ALTER TABLE public.outbound_commits
          ADD COLUMN platform VARCHAR(32) NOT NULL DEFAULT '';
        ALTER TABLE public.outbound_commits
          ALTER COLUMN platform DROP DEFAULT;
      END IF;

      -- shop_id
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='shop_id'
      ) THEN
        ALTER TABLE public.outbound_commits
          ADD COLUMN shop_id VARCHAR(64) NOT NULL DEFAULT '';
        ALTER TABLE public.outbound_commits
          ALTER COLUMN shop_id DROP DEFAULT;
      END IF;
    END $$;
    """))

    # 2) 删除旧索引（若历史存在三列版）
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_indexes
         WHERE schemaname='public' AND indexname='ux_outbound_commits_3cols'
      ) THEN
        EXECUTE 'DROP INDEX public.ux_outbound_commits_3cols';
      END IF;
    END $$;
    """))

    # 3) 创建 4 列唯一索引（不存在才创建）
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
         WHERE schemaname='public' AND indexname='ux_outbound_commits_4cols'
      ) THEN
        EXECUTE 'CREATE UNIQUE INDEX ux_outbound_commits_4cols
                  ON public.outbound_commits(platform, shop_id, ref, state)';
      END IF;
    END $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # 先安全删除 4 列唯一索引
    conn.execute(sa.text("DROP INDEX IF EXISTS public.ux_outbound_commits_4cols"))

    # 仅当列存在且无依赖时再尝试删除列（一般 CI 回滚不要求强删列，保守处理）
    conn.execute(sa.text("""
    DO $$
    BEGIN
      -- shop_id 列：存在才删（若其它对象依赖则跳过）
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='shop_id'
      ) THEN
        BEGIN
          ALTER TABLE public.outbound_commits DROP COLUMN shop_id;
        EXCEPTION
          WHEN others THEN
            -- 有依赖则跳过，不影响回滚流程
            RAISE NOTICE 'skip drop outbound_commits.shop_id due to dependency';
        END;
      END IF;

      -- platform 列：存在才删（同上）
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='platform'
      ) THEN
        BEGIN
          ALTER TABLE public.outbound_commits DROP COLUMN platform;
        EXCEPTION
          WHEN others THEN
            RAISE NOTICE 'skip drop outbound_commits.platform due to dependency';
        END;
      END IF;

      -- 历史兼容：若需要回到 3 列唯一索引形态，可在此按需重建（默认不重建）
      -- IF NOT EXISTS (
      --   SELECT 1 FROM pg_indexes
      --    WHERE schemaname='public' AND indexname='ux_outbound_commits_3cols'
      -- ) THEN
      --   EXECUTE 'CREATE UNIQUE INDEX ux_outbound_commits_3cols
      --             ON public.outbound_commits(ref, state, /*其他历史列*/)';
      -- END IF;
    END $$;
    """))
