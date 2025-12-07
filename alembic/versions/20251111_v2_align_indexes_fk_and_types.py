"""v2 align: add indexes/FKs; fix ledger types & nullable

Revision ID: 20251111_v2_align_indexes_fk_and_types
Revises: 20251111_drop_legacy_nobatch_unique
Create Date: 2025-11-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251111_v2_align_indexes_fk_and_types"
down_revision = "20251111_drop_legacy_nobatch_unique"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1) batches: 索引 + 外键
    # ------------------------------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE c.relname='ix_batches_production_date' AND n.nspname='public'
            ) THEN
                CREATE INDEX ix_batches_production_date ON batches (production_date);
            END IF;
        END$$;
    """)

    # 外键 item_id -> items.id （若已存在则跳过）
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                WHERE tc.table_schema='public'
                  AND tc.table_name='batches'
                  AND tc.constraint_type='FOREIGN KEY'
            ) THEN
                ALTER TABLE batches
                ADD CONSTRAINT fk_batches_item
                FOREIGN KEY (item_id) REFERENCES items(id);
            END IF;
        END$$;
    """)

    # 2) stock_ledger: ref 置为 NOT NULL；delta/after_qty 改为 integer；新增索引
    # ------------------------------------------------------------------
    # 2.1 先填充 ref 的空值，避免 set not null 失败
    op.execute("""
        UPDATE stock_ledger
           SET ref = CONCAT('MIGR-', id)
         WHERE ref IS NULL;
    """)

    # 2.2 修改 ref 为空禁止
    op.alter_column("stock_ledger", "ref", existing_type=sa.String(length=128), nullable=False)

    # 2.3 类型变更 DOUBLE PRECISION -> INTEGER（安全转换：四舍五入）
    op.execute("""
        ALTER TABLE stock_ledger
        ALTER COLUMN delta     TYPE INTEGER USING ROUND(delta)::INTEGER,
        ALTER COLUMN after_qty TYPE INTEGER USING ROUND(after_qty)::INTEGER;
    """)

    # 2.4 新增索引（若不存在）
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE c.relname='ix_stock_ledger_batch_code' AND n.nspname='public'
            ) THEN
                CREATE INDEX ix_stock_ledger_batch_code ON stock_ledger (batch_code);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE c.relname='ix_stock_ledger_warehouse_id' AND n.nspname='public'
            ) THEN
                CREATE INDEX ix_stock_ledger_warehouse_id ON stock_ledger (warehouse_id);
            END IF;
        END$$;
    """)

    # 3) stocks: 新增索引 + 外键
    # ------------------------------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE c.relname='ix_stocks_item_id' AND n.nspname='public'
            ) THEN
                CREATE INDEX ix_stocks_item_id ON stocks (item_id);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE c.relname='ix_stocks_warehouse_id' AND n.nspname='public'
            ) THEN
                CREATE INDEX ix_stocks_warehouse_id ON stocks (warehouse_id);
            END IF;
        END$$;
    """)

    # 外键 stocks.warehouse_id -> warehouses.id （若不存在）
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                WHERE tc.table_schema='public'
                  AND tc.table_name='stocks'
                  AND tc.constraint_type='FOREIGN KEY'
            ) THEN
                ALTER TABLE stocks
                ADD CONSTRAINT fk_stocks_warehouse
                FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE RESTRICT;
            END IF;
        END$$;
    """)


def downgrade():
    # 回退：删除本迁移新增的索引/外键；类型回退为 double precision；ref 允许为空
    op.execute("DROP INDEX IF EXISTS ix_batches_production_date;")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema='public' AND table_name='batches'
                  AND constraint_name='fk_batches_item'
            ) THEN
                ALTER TABLE batches DROP CONSTRAINT fk_batches_item;
            END IF;
        END$$;
    """)

    op.execute("DROP INDEX IF EXISTS ix_stock_ledger_batch_code;")
    op.execute("DROP INDEX IF EXISTS ix_stock_ledger_warehouse_id;")
    op.execute("""
        ALTER TABLE stock_ledger
        ALTER COLUMN delta     TYPE DOUBLE PRECISION USING delta::double precision,
        ALTER COLUMN after_qty TYPE DOUBLE PRECISION USING after_qty::double precision;
    """)
    op.alter_column("stock_ledger", "ref", nullable=True, existing_type=sa.String(length=128))

    op.execute("DROP INDEX IF EXISTS ix_stocks_item_id;")
    op.execute("DROP INDEX IF EXISTS ix_stocks_warehouse_id;")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema='public' AND table_name='stocks'
                  AND constraint_name='fk_stocks_warehouse'
            ) THEN
                ALTER TABLE stocks DROP CONSTRAINT fk_stocks_warehouse;
            END IF;
        END$$;
    """)
