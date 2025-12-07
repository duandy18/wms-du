"""seed SKU-001 as baseline item (id auto)

Revision ID: 20251106_seed_sku_001
Revises: 20251106_merge_heads_unify_bootstrap_and_itemsid
Create Date: 2025-11-06 16:45:00+08
"""

from alembic import op

revision = "20251106_seed_sku_001"
down_revision = "20251106_merge_heads_unify_bootstrap_and_itemsid"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    DO $$
    BEGIN
      -- 如果还没有 SKU-001，则插入一条（让 id 按当前序列自动增长）
      IF NOT EXISTS (SELECT 1 FROM public.items WHERE sku = 'SKU-001') THEN
        INSERT INTO public.items (sku, name, unit) VALUES ('SKU-001', 'X猫粮', 'EA');
      END IF;

      -- 对齐 items.id 序列位置（无论是 identity 还是 sequence+default 都安全）
      PERFORM setval(
        pg_get_serial_sequence('public.items','id'),
        COALESCE((SELECT MAX(id) FROM public.items), 0), true
      );
    END $$;
    """)


def downgrade():
    # 回滚时不删除数据，保持幂等与安全；若确需删除，可改为：
    # op.execute("DELETE FROM public.items WHERE sku='SKU-001';")
    pass
