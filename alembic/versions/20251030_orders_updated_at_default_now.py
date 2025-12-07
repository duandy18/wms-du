"""orders.updated_at: set DEFAULT now() and backfill (idempotent)

Revision ID: 20251030_orders_updated_at_default_now
Revises: 20251030_orders_total_amount_default_zero
Create Date: 2025-10-30 10:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20251030_orders_updated_at_default_now"
down_revision = "20251030_orders_total_amount_default_zero"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    目标：若存在 orders 表，则确保有 updated_at 列；设置 DEFAULT now() 并一次性回填空值。
    说明：使用 to_regclass/ information_schema 守卫，避免 UndefinedTable/UndefinedColumn。
    """
    conn = op.get_bind()
    conn.execute(
        sa.text("""
    DO $$
    BEGIN
      IF to_regclass('public.orders') IS NOT NULL THEN

        -- 若列不存在，先补列
        IF NOT EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='updated_at'
        ) THEN
          ALTER TABLE public.orders ADD COLUMN updated_at timestamptz;
        END IF;

        -- 设置默认值并回填空值
        ALTER TABLE public.orders ALTER COLUMN updated_at SET DEFAULT now();
        EXECUTE 'UPDATE public.orders SET updated_at = now() WHERE updated_at IS NULL';

        -- （可选）若你不希望保留默认，可在后续迁移再统一 DROP DEFAULT
        -- 当前保留默认，方便后续写入
      END IF;
    END$$;
    """)
    )


def downgrade() -> None:
    """
    回滚：仅当 orders.updated_at 存在时，移除 DEFAULT（不删列）。
    """
    conn = op.get_bind()
    conn.execute(
        sa.text("""
    DO $$
    BEGIN
      IF to_regclass('public.orders') IS NOT NULL THEN
        IF EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='updated_at'
        ) THEN
          ALTER TABLE public.orders ALTER COLUMN updated_at DROP DEFAULT;
        END IF;
      END IF;
    END$$;
    """)
    )
