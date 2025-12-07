"""outbound_commits: add shop_id/platform/state (guarded) + create 4-col unique index

Revision ID: u3_outbound_commits_shop_id
Revises: u2_event_error_log_message_text
Create Date: 2025-10-?? ??

本迁移目标：
- 为 public.outbound_commits 补齐列：
  - platform   VARCHAR(32)   NOT NULL（临时默认 ''，随后移除默认）
  - shop_id    VARCHAR(64)   NOT NULL（临时默认 ''，随后移除默认）
  - state      VARCHAR(32)   NOT NULL（临时默认 'COMMIT'，随后移除默认）
- 若存在历史 3 列唯一索引 ux_outbound_commits_3cols，则先删除
- 在上述三列均存在时，创建 4 列唯一索引 ux_outbound_commits_4cols (platform, shop_id, ref, state)

降级：
- 删除 4 列唯一索引（若存在）
- 在无依赖对象时，尝试删除 platform / shop_id / state（三列分别独立判定）
- 有依赖则跳过并给 NOTICE，不做强制 CASCADE
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision: str = "u3_outbound_commits_shop_id"
down_revision: str | None = "u2_event_error_log_message_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 表不存在时直接跳过（兼容精简链路）
    conn.execute(
        sa.text("""
    DO $$
    BEGIN
      IF to_regclass('public.outbound_commits') IS NULL THEN
        RAISE NOTICE 'skip: table public.outbound_commits not found';
        RETURN;
      END IF;

      -- 1) 列缺失则补齐（临时默认 -> 立刻移除默认），全部使用信息架构守卫
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='platform'
      ) THEN
        ALTER TABLE public.outbound_commits ADD COLUMN platform VARCHAR(32) NOT NULL DEFAULT '';
        ALTER TABLE public.outbound_commits ALTER COLUMN platform DROP DEFAULT;
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='shop_id'
      ) THEN
        ALTER TABLE public.outbound_commits ADD COLUMN shop_id VARCHAR(64) NOT NULL DEFAULT '';
        ALTER TABLE public.outbound_commits ALTER COLUMN shop_id DROP DEFAULT;
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='state'
      ) THEN
        ALTER TABLE public.outbound_commits ADD COLUMN state VARCHAR(32) NOT NULL DEFAULT 'COMMIT';
        ALTER TABLE public.outbound_commits ALTER COLUMN state DROP DEFAULT;
      END IF;

      -- 2) 历史 3 列唯一索引（若存在）先删除
      IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='public' AND indexname='ux_outbound_commits_3cols'
      ) THEN
        DROP INDEX public.ux_outbound_commits_3cols;
      END IF;

      -- 3) 仅当 3 列都存在时，创建 4 列唯一索引（不存在才建）
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='outbound_commits'
           AND column_name IN ('platform','shop_id','state')
        GROUP BY table_schema, table_name
        HAVING COUNT(*) = 3
      ) THEN
        IF NOT EXISTS (
          SELECT 1 FROM pg_indexes
          WHERE schemaname='public' AND indexname='ux_outbound_commits_4cols'
        ) THEN
          CREATE UNIQUE INDEX ux_outbound_commits_4cols
            ON public.outbound_commits(platform, shop_id, ref, state);
        END IF;
      ELSE
        RAISE NOTICE 'skip: not creating ux_outbound_commits_4cols because some columns are missing';
      END IF;
    END $$;
    """)
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text("""
    DO $$
    DECLARE
      dep_count int;
    BEGIN
      IF to_regclass('public.outbound_commits') IS NULL THEN
        RAISE NOTICE 'skip: table public.outbound_commits not found';
        RETURN;
      END IF;

      -- 1) 删 4 列唯一索引（若存在）
      IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='public' AND indexname='ux_outbound_commits_4cols'
      ) THEN
        DROP INDEX public.ux_outbound_commits_4cols;
      END IF;

      -- 2) 逐列尝试删除（有依赖则跳过）
      -- platform
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='platform'
      ) THEN
        SELECT COUNT(*) INTO dep_count
        FROM pg_depend d
        JOIN pg_class c ON c.oid = d.refobjid
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.refobjsubid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='public' AND c.relname='outbound_commits' AND a.attname='platform';
        IF dep_count = 0 THEN
          ALTER TABLE public.outbound_commits DROP COLUMN platform;
        ELSE
          RAISE NOTICE 'skip drop column outbound_commits.platform due to dependency';
        END IF;
      END IF;

      -- shop_id
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='shop_id'
      ) THEN
        SELECT COUNT(*) INTO dep_count
        FROM pg_depend d
        JOIN pg_class c ON c.oid = d.refobjid
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.refobjsubid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='public' AND c.relname='outbound_commits' AND a.attname='shop_id';
        IF dep_count = 0 THEN
          ALTER TABLE public.outbound_commits DROP COLUMN shop_id;
        ELSE
          RAISE NOTICE 'skip drop column outbound_commits.shop_id due to dependency';
        END IF;
      END IF;

      -- state
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='outbound_commits' AND column_name='state'
      ) THEN
        SELECT COUNT(*) INTO dep_count
        FROM pg_depend d
        JOIN pg_class c ON c.oid = d.refobjid
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.refobjsubid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname='public' AND c.relname='outbound_commits' AND a.attname='state';
        IF dep_count = 0 THEN
          ALTER TABLE public.outbound_commits DROP COLUMN state;
        ELSE
          RAISE NOTICE 'skip drop column outbound_commits.state due to dependency';
        END IF;
      END IF;
    END $$;
    """)
    )
