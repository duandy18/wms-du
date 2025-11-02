"""schema additions batch-3 (orders cols + snapshots batch link)

Revision ID: bf539dde5f39
Revises: d16674198fd0
Create Date: 2025-10-30 09:40:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "bf539dde5f39"
down_revision = "d16674198fd0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 仅当 orders 表存在时才做列补齐，避免 UndefinedTable
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF to_regclass('public.orders') IS NOT NULL THEN

        -- order_no
        IF NOT EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='order_no'
        ) THEN
          ALTER TABLE public.orders ADD COLUMN order_no VARCHAR(64);
        END IF;

        -- client_ref
        IF NOT EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='client_ref'
        ) THEN
          ALTER TABLE public.orders ADD COLUMN client_ref VARCHAR(64);
        END IF;

        -- status
        IF NOT EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='status'
        ) THEN
          ALTER TABLE public.orders ADD COLUMN status VARCHAR(32);
        END IF;

        -- created_at
        IF NOT EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='created_at'
        ) THEN
          ALTER TABLE public.orders ADD COLUMN created_at timestamptz DEFAULT now();
          ALTER TABLE public.orders ALTER COLUMN created_at DROP DEFAULT;
        END IF;

        -- updated_at
        IF NOT EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='updated_at'
        ) THEN
          ALTER TABLE public.orders ADD COLUMN updated_at timestamptz;
        END IF;

      END IF;
    END$$;
    """))

    # 如果本迁移还需要给其它表/视图打补丁，也按上述模式加 to_regclass 守卫后执行
    # …（略）


def downgrade() -> None:
    conn = op.get_bind()

    # 同样仅当 orders 表存在时再尝试回滚列（幂等）
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF to_regclass('public.orders') IS NOT NULL THEN

        -- 回滚时按需删除列（若你希望可逆）
        IF EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='updated_at'
        ) THEN
          ALTER TABLE public.orders DROP COLUMN updated_at;
        END IF;

        IF EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='created_at'
        ) THEN
          ALTER TABLE public.orders DROP COLUMN created_at;
        END IF;

        IF EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='status'
        ) THEN
          ALTER TABLE public.orders DROP COLUMN status;
        END IF;

        IF EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='client_ref'
        ) THEN
          ALTER TABLE public.orders DROP COLUMN client_ref;
        END IF;

        IF EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='order_no'
        ) THEN
          ALTER TABLE public.orders DROP COLUMN order_no;
        END IF;

      END IF;
    END$$;
    """))
