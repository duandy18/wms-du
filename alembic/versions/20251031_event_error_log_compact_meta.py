"""event_error_log compact meta (move verbose cols into meta JSONB) + CI-safe downgrade

Revision ID: 20251031_event_error_log_compact_meta
Revises: 20251030_events_core_tables
Create Date: 2025-10-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision = "20251031_event_error_log_compact_meta"
down_revision = "20251030_events_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 确保 meta 列存在（JSONB）
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='event_error_log' AND column_name='meta'
      ) THEN
        ALTER TABLE public.event_error_log ADD COLUMN meta JSONB;
      END IF;
    END$$;"""))

    # 2) 将“冗余列”合并进 meta（仅当这些列存在时才采集）
    #   说明：这里尽量只聚合，不在此处删除；删除放到步骤 4 并带守卫
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='error_code') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('error_code', error_code);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='error_type') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('error_type', error_type);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='error_msg') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('error_msg', error_msg);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='message') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('message', message);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='event_id') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('event_id', event_id);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='order_no') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('order_no', order_no);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='shop_id') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('shop_id', shop_id);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='platform') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('platform', platform);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='from_state') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('from_state', from_state);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='to_state') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('to_state', to_state);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='idempotency_key') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('idempotency_key', idempotency_key);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='payload') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('payload', payload);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='payload_json') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('payload_json', payload_json);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='retry_count') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('retry_count', retry_count);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='max_retries') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('max_retries', max_retries);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='created_at') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('created_at', created_at);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='updated_at') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('updated_at', updated_at);
      END IF;
      IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='next_retry_at') THEN
        UPDATE public.event_error_log
           SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object('next_retry_at', next_retry_at);
      END IF;
    END$$;"""))

    # 3) 为 meta 建 GIN 索引（如需）
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_event_error_log_meta_gin ON event_error_log USING gin (meta)"))

    # 4) 删除已合并到 meta 的旧列（带守卫）
    cols = (
        "error_code,error_type,error_msg,message,event_id,order_no,shop_id,platform,from_state,to_state,"
        "idempotency_key,payload,payload_json,retry_count,max_retries,created_at,updated_at,next_retry_at"
    ).split(",")
    for c in cols:
        op.execute(sa.text(f"ALTER TABLE event_error_log DROP COLUMN IF EXISTS {c}"))


def downgrade() -> None:
    conn = op.get_bind()

    # 1) 先补回旧列（若缺）
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='error_code') THEN
        ALTER TABLE public.event_error_log ADD COLUMN error_code TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='error_type') THEN
        ALTER TABLE public.event_error_log ADD COLUMN error_type TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='error_msg') THEN
        ALTER TABLE public.event_error_log ADD COLUMN error_msg TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='message') THEN
        ALTER TABLE public.event_error_log ADD COLUMN message TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='event_id') THEN
        ALTER TABLE public.event_error_log ADD COLUMN event_id TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='order_no') THEN
        ALTER TABLE public.event_error_log ADD COLUMN order_no TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='shop_id') THEN
        ALTER TABLE public.event_error_log ADD COLUMN shop_id TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='platform') THEN
        ALTER TABLE public.event_error_log ADD COLUMN platform TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='from_state') THEN
        ALTER TABLE public.event_error_log ADD COLUMN from_state TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='to_state') THEN
        ALTER TABLE public.event_error_log ADD COLUMN to_state TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='idempotency_key') THEN
        ALTER TABLE public.event_error_log ADD COLUMN idempotency_key TEXT;
      END IF;
      -- payload: 历史有 text/bytea 等，这里按 TEXT 回填
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='payload') THEN
        ALTER TABLE public.event_error_log ADD COLUMN payload TEXT;
      END IF;
      -- payload_json: 历史有 text/jsonb 两种，先加 TEXT，稍后根据实际类型回填后可按需改型
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='payload_json') THEN
        ALTER TABLE public.event_error_log ADD COLUMN payload_json TEXT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='retry_count') THEN
        ALTER TABLE public.event_error_log ADD COLUMN retry_count INT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='max_retries') THEN
        ALTER TABLE public.event_error_log ADD COLUMN max_retries INT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='created_at') THEN
        ALTER TABLE public.event_error_log ADD COLUMN created_at TIMESTAMPTZ;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='updated_at') THEN
        ALTER TABLE public.event_error_log ADD COLUMN updated_at TIMESTAMPTZ;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='event_error_log' AND column_name='next_retry_at') THEN
        ALTER TABLE public.event_error_log ADD COLUMN next_retry_at TIMESTAMPTZ;
      END IF;
    END$$;"""))

    # 2) 从 meta 回填各列（text/int/timestamptz 用 ->> 并显式强转）
    conn.execute(sa.text("""
    UPDATE public.event_error_log
       SET error_code      = COALESCE(NULLIF(meta->>'error_code',''), error_code),
           error_type      = COALESCE(NULLIF(meta->>'error_type',''), error_type),
           error_msg       = COALESCE(NULLIF(meta->>'error_msg',''), error_msg),
           message         = COALESCE(NULLIF(meta->>'message',''), message),
           event_id        = COALESCE(NULLIF(meta->>'event_id',''), event_id),
           order_no        = COALESCE(NULLIF(meta->>'order_no',''), order_no),
           shop_id         = COALESCE(NULLIF(meta->>'shop_id',''), shop_id),
           platform        = COALESCE(NULLIF(meta->>'platform',''), platform),
           from_state      = COALESCE(NULLIF(meta->>'from_state',''), from_state),
           to_state        = COALESCE(NULLIF(meta->>'to_state',''), to_state),
           idempotency_key = COALESCE(NULLIF(meta->>'idempotency_key',''), idempotency_key),
           payload         = COALESCE(NULLIF(meta->>'payload',''), payload),
           retry_count     = COALESCE(NULLIF(meta->>'retry_count','')::int, retry_count),
           max_retries     = COALESCE(NULLIF(meta->>'max_retries','')::int, max_retries),
           created_at      = COALESCE(NULLIF(meta->>'created_at','')::timestamptz, created_at),
           updated_at      = COALESCE(NULLIF(meta->>'updated_at','')::timestamptz, updated_at),
           next_retry_at   = COALESCE(NULLIF(meta->>'next_retry_at','')::timestamptz, next_retry_at)
    """))

    # 3) payload_json 回填：根据列真实类型选择 text / jsonb 两种路径，避免 COALESCE 类型不一致
    conn.execute(sa.text("""
    DO $$
    DECLARE is_jsonb boolean;
    BEGIN
      SELECT (data_type='jsonb')
        INTO is_jsonb
        FROM information_schema.columns
       WHERE table_schema='public' AND table_name='event_error_log' AND column_name='payload_json'
       LIMIT 1;

      IF is_jsonb THEN
        -- 目标列是 jsonb：把 meta->>'payload_json' 解析为 jsonb，再回填
        EXECUTE $SQL$
          UPDATE public.event_error_log
             SET payload_json = COALESCE(NULLIF(meta->>'payload_json','')::jsonb, payload_json)
        $SQL$;
      ELSE
        -- 目标列是 text：走纯文本
        EXECUTE $SQL$
          UPDATE public.event_error_log
             SET payload_json = COALESCE(NULLIF(meta->>'payload_json',''), payload_json)
        $SQL$;
      END IF;
    END$$;"""))

    # 4) 删 meta 索引（如果有）
    op.execute(sa.text("DROP INDEX IF EXISTS ix_event_error_log_meta_gin"))

    # 5) 如不再需要 meta，可按需删除（这里保留；若一定要删，可打开下行）
    # op.execute(sa.text("ALTER TABLE event_error_log DROP COLUMN IF EXISTS meta"))
