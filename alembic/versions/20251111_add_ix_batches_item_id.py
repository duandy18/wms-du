"""v2: add index ix_batches_item_id"""

from alembic import op

# 你的新修订号
revision = "20251111_add_ix_batches_item_id"
down_revision = "b1a483b58d1e"  # ← 用 heads -v 打印的当前 head
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 幂等创建（存在则跳过）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1
        FROM   pg_class c
        JOIN   pg_namespace n ON n.oid=c.relnamespace
        WHERE  c.relname='ix_batches_item_id'
          AND  n.nspname='public'
      ) THEN
        CREATE INDEX ix_batches_item_id ON public.batches (item_id);
      END IF;
    END$$;
    """)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.ix_batches_item_id;")
