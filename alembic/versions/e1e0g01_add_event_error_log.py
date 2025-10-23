"""add event_error_log table (idempotent & aligned with model)"""

from alembic import op

# 保持你原有的 revision / down_revision
revision = "e1e0g01"
down_revision = "20251016_add_outbound_commits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 幂等：若表已存在则补齐缺失列；索引不存在再创建
    op.execute(
        r"""
        DO $$
        BEGIN
          -- 1) 若表不存在则直接创建为“新结构”
          IF to_regclass('public.event_error_log') IS NULL THEN
            CREATE TABLE public.event_error_log (
              id              BIGSERIAL PRIMARY KEY,
              platform        VARCHAR(32)  NOT NULL,
              shop_id         VARCHAR(64)  NOT NULL,
              order_no        VARCHAR(128) NOT NULL,
              idempotency_key VARCHAR(256) NOT NULL,
              from_state      VARCHAR(32),
              to_state        VARCHAR(32)  NOT NULL,
              error_code      VARCHAR(64)  NOT NULL,
              error_msg       TEXT,
              payload_json    JSONB,
              retry_count     INTEGER      NOT NULL DEFAULT 0,
              max_retries     INTEGER      NOT NULL DEFAULT 5,
              next_retry_at   TIMESTAMPTZ,
              created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
              updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
            );
          ELSE
            -- 2) 表已存在：逐列补齐（老表可能只有 platform/event_id/error_type/message/payload/created_at 等）
            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='shop_id'
            ) THEN
              ALTER TABLE public.event_error_log
                ADD COLUMN shop_id VARCHAR(64) NOT NULL DEFAULT '';
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='order_no'
            ) THEN
              ALTER TABLE public.event_error_log
                ADD COLUMN order_no VARCHAR(128) NOT NULL DEFAULT '';
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='idempotency_key'
            ) THEN
              ALTER TABLE public.event_error_log
                ADD COLUMN idempotency_key VARCHAR(256) NOT NULL DEFAULT '';
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='from_state'
            ) THEN
              ALTER TABLE public.event_error_log
                ADD COLUMN from_state VARCHAR(32);
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='to_state'
            ) THEN
              ALTER TABLE public.event_error_log
                ADD COLUMN to_state VARCHAR(32) NOT NULL DEFAULT 'VOID';
            END IF;

            -- 兼容早期命名：error_type/message/payload → 对齐 error_code/error_msg/payload_json
            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='error_code'
            ) THEN
              -- 若存在旧列 error_type 则以其为源，否则直接加新列
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='event_error_log' AND column_name='error_type'
              ) THEN
                ALTER TABLE public.event_error_log ADD COLUMN error_code VARCHAR(64);
                UPDATE public.event_error_log SET error_code = error_type WHERE error_code IS NULL;
              ELSE
                ALTER TABLE public.event_error_log ADD COLUMN error_code VARCHAR(64) NOT NULL DEFAULT 'ERROR';
              END IF;
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='error_msg'
            ) THEN
              -- 若存在旧列 message 则搬运到 error_msg
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='event_error_log' AND column_name='message'
              ) THEN
                ALTER TABLE public.event_error_log ADD COLUMN error_msg TEXT;
                UPDATE public.event_error_log SET error_msg = message WHERE error_msg IS NULL;
              ELSE
                ALTER TABLE public.event_error_log ADD COLUMN error_msg TEXT;
              END IF;
            END IF;

            -- payload → payload_json（若旧列 payload 存在且为 JSON/JSONB，用 CAST 迁移；否则仅补列）
            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='payload_json'
            ) THEN
              ALTER TABLE public.event_error_log ADD COLUMN payload_json JSONB;
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='event_error_log' AND column_name='payload'
              ) THEN
                -- 尝试将旧 payload 搬到新列（尽力而为，不成功也不报错）
                BEGIN
                  UPDATE public.event_error_log SET payload_json = payload::jsonb
                  WHERE payload_json IS NULL;
                EXCEPTION WHEN others THEN
                  -- 忽略非 JSON 内容导致的异常
                  PERFORM 1;
                END;
              END IF;
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='retry_count'
            ) THEN
              ALTER TABLE public.event_error_log ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='max_retries'
            ) THEN
              ALTER TABLE public.event_error_log ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 5;
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='next_retry_at'
            ) THEN
              ALTER TABLE public.event_error_log ADD COLUMN next_retry_at TIMESTAMPTZ;
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='created_at'
            ) THEN
              ALTER TABLE public.event_error_log ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();
            END IF;

            IF NOT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='event_error_log' AND column_name='updated_at'
            ) THEN
              ALTER TABLE public.event_error_log ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
            END IF;
          END IF;

          -- 3) 关键联合索引（平台/店铺/幂等键）—— 现在列已保证存在
          IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = 'ix_event_error_log_key'
          ) THEN
            CREATE INDEX ix_event_error_log_key
              ON public.event_error_log(platform, shop_id, idempotency_key);
          END IF;

          -- 4) 重试候选部分索引（仅 PG）
          IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = 'ix_event_error_log_retry'
          ) THEN
            CREATE INDEX ix_event_error_log_retry
              ON public.event_error_log(next_retry_at)
              WHERE retry_count < max_retries;
          END IF;

        END$$;
        """
    )


def downgrade() -> None:
    # 默认不删除表；如需回退，自行按需 drop
    pass
