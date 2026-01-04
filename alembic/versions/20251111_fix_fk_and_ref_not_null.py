"""v2 fix: add missing FKs; make stock_ledger.ref NOT NULL

Revision ID: 20251111_fix_fk_and_ref_not_null
Revises: bca5b19ea75a
Create Date: 2025-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "20251111_fix_fk_and_ref_not_null"
down_revision = "bca5b19ea75a"
branch_labels = None
depends_on = None


def upgrade():

    # 1) 回填并强制非空：stock_ledger.ref
    op.execute("""
        UPDATE public.stock_ledger
           SET ref = 'MIGR-' || id
         WHERE ref IS NULL
    """)
    op.alter_column(
        "stock_ledger",
        "ref",
        existing_type=sa.String(length=128),
        nullable=False,
        schema="public",
    )

    # 2) batches.item_id -> items(id) 外键（若不存在才创建）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
         WHERE c.conname = 'fk_batches_item'
           AND c.conrelid = 'public.batches'::regclass
      ) THEN
        ALTER TABLE public.batches
          ADD CONSTRAINT fk_batches_item
          FOREIGN KEY (item_id) REFERENCES public.items(id);
      END IF;
    END$$;
    """)

    # 3) stocks.warehouse_id -> warehouses(id) 外键（若不存在才创建）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
         WHERE c.conname = 'fk_stocks_warehouse'
           AND c.conrelid = 'public.stocks'::regclass
      ) THEN
        ALTER TABLE public.stocks
          ADD CONSTRAINT fk_stocks_warehouse
          FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id) ON DELETE RESTRICT;
      END IF;
    END$$;
    """)


def downgrade():
    # 回滚外键与非空（可选）
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint c
         WHERE c.conname = 'fk_batches_item'
           AND c.conrelid = 'public.batches'::regclass
      ) THEN
        ALTER TABLE public.batches DROP CONSTRAINT fk_batches_item;
      END IF;
    END$$;
    """)
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint c
         WHERE c.conname = 'fk_stocks_warehouse'
           AND c.conrelid = 'public.stocks'::regclass
      ) THEN
        ALTER TABLE public.stocks DROP CONSTRAINT fk_stocks_warehouse;
      END IF;
    END$$;
    """)
    op.alter_column(
        "stock_ledger",
        "ref",
        existing_type=sa.String(length=128),
        nullable=True,
        schema="public",
    )
