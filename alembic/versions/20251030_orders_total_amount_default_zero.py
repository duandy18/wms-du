"""orders.total_amount: set DEFAULT 0 and backfill (idempotent)

Revision ID: 20251030_orders_total_amount_default_zero
Revises: 20251030_orders_add_minimal_columns
Create Date: 2025-10-30 10:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20251030_orders_total_amount_default_zero"
down_revision = "20251030_orders_add_minimal_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    若存在 orders 表，则确保有 total_amount 列；设置 DEFAULT 0 并回填空值。
    """
    conn = op.get_bind()
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF to_regclass('public.orders') IS NOT NULL THEN

        -- 若列不存在，先补列（numeric(18,6) 可按你的实际精度调整）
        IF NOT EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='total_amount'
        ) THEN
          ALTER TABLE public.orders ADD COLUMN total_amount numeric(18,6);
        END IF;

        -- 设置默认 0 并回填空值
        ALTER TABLE public.orders ALTER COLUMN total_amount SET DEFAULT 0;
        EXECUTE 'UPDATE public.orders SET total_amount = 0 WHERE total_amount IS NULL';

      END IF;
    END$$;
    """))


def downgrade() -> None:
    """
    仅当 orders.total_amount 存在时，移除 DEFAULT（不删列），避免 UndefinedColumn。
    """
    conn = op.get_bind()
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF to_regclass('public.orders') IS NOT NULL THEN
        IF EXISTS (
          SELECT 1 FROM information_schema.columns
           WHERE table_schema='public' AND table_name='orders' AND column_name='total_amount'
        ) THEN
          ALTER TABLE public.orders ALTER COLUMN total_amount DROP DEFAULT;
        END IF;
      END IF;
    END$$;
    """))
