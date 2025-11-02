"""schema additions batch-3 (orders cols + snapshots batch link)

Revision ID: bf539dde5f39
Revises: d16674198fd0
Create Date: 2025-10-30 07:29:15.021416
"""
from alembic import op
import sqlalchemy as sa


revision = "bf539dde5f39"
down_revision = "d16674198fd0"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ------------------------------
    # A) orders：新增业务字段 + 索引
    # ------------------------------
    for col, coltype in [
        ("order_no", sa.String(64)),
        ("order_type", sa.String(32)),
        ("status", sa.String(32)),
        ("customer_name", sa.String(128)),
        ("supplier_name", sa.String(128)),
    ]:
        conn.execute(sa.text(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='orders' AND column_name='{col}'
                ) THEN
                    ALTER TABLE public.orders ADD COLUMN {col} {coltype.compile(dialect=sa.dialects.postgresql.dialect())};
                END IF;
            END $$;
        """))

    # total_amount
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='orders' AND column_name='total_amount'
            ) THEN
                ALTER TABLE public.orders ADD COLUMN total_amount numeric(12,2) NOT NULL DEFAULT 0;
                ALTER TABLE public.orders ALTER COLUMN total_amount DROP DEFAULT;
            END IF;
        END $$;
    """))

    # updated_at
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='orders' AND column_name='updated_at'
            ) THEN
                ALTER TABLE public.orders ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
                ALTER TABLE public.orders ALTER COLUMN updated_at DROP DEFAULT;
            END IF;
        END $$;
    """))

    # 幂等索引
    for name, cols in [
        ("ix_orders_order_no", "(order_no)"),
        ("ix_orders_order_type", "(order_type)"),
        ("ix_orders_status", "(status)"),
        ("ix_orders_type_status", "(order_type, status)"),
    ]:
        conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {name} ON public.orders {cols}"))

    # ------------------------------
    # B) stock_snapshots：批次关联增强
    # ------------------------------
    # 批次列
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='stock_snapshots' AND column_name='batch_id'
            ) THEN
                ALTER TABLE public.stock_snapshots ADD COLUMN batch_id integer NULL;
            END IF;
        END $$;
    """))

    # qty_allocated / expiry_date / age_days
    for col, coldef in [
        ("qty_allocated", "integer NOT NULL DEFAULT 0"),
        ("expiry_date", "date NULL"),
        ("age_days", "integer NULL"),
    ]:
        conn.execute(sa.text(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='stock_snapshots' AND column_name='{col}'
                ) THEN
                    ALTER TABLE public.stock_snapshots ADD COLUMN {col} {coldef};
                    IF '{col}' = 'qty_allocated' THEN
                        ALTER TABLE public.stock_snapshots ALTER COLUMN qty_allocated DROP DEFAULT;
                    END IF;
                END IF;
            END $$;
        """))

    # 索引 & 外键
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_stock_snapshots_batch_id ON public.stock_snapshots (batch_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_ss_item_date ON public.stock_snapshots (item_id, snapshot_date)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_ss_wh_date ON public.stock_snapshots (warehouse_id, snapshot_date)"))
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname='fk_ss_batch'
            ) THEN
                ALTER TABLE ONLY public.stock_snapshots
                ADD CONSTRAINT fk_ss_batch FOREIGN KEY (batch_id)
                REFERENCES public.batches(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """))


def downgrade():
    # 仅撤销新增列与索引，不触碰老结构
    for idx in [
        "ix_orders_order_no", "ix_orders_order_type", "ix_orders_status", "ix_orders_type_status",
        "ix_stock_snapshots_batch_id", "ix_ss_item_date", "ix_ss_wh_date"
    ]:
        op.execute(sa.text(f"DROP INDEX IF EXISTS public.{idx}"))

    for col in [
        "order_no", "order_type", "status", "customer_name", "supplier_name",
        "total_amount", "updated_at"
    ]:
        op.execute(sa.text(f"ALTER TABLE public.orders DROP COLUMN IF EXISTS {col}"))

    for col in ["batch_id", "qty_allocated", "expiry_date", "age_days"]:
        op.execute(sa.text(f"ALTER TABLE public.stock_snapshots DROP COLUMN IF EXISTS {col}"))

    op.execute(sa.text("ALTER TABLE public.stock_snapshots DROP CONSTRAINT IF EXISTS fk_ss_batch"))
