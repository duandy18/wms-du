"""ensure items.id default + seed SKU-001 baseline (plain SQL, idempotent)

Revision ID: 20251106_fix_items_id_and_seed_sku001
Revises: 20251106_seed_sku_001
Create Date: 2025-11-06 17:20:00+08
"""

from alembic import op

revision = "20251106_fix_items_id_and_seed_sku001"
down_revision = "20251106_seed_sku_001"
branch_labels = None
depends_on = None


def upgrade():
    # 1) 确保序列存在（CREATE SEQUENCE IF NOT EXISTS 是幂等的）
    op.execute("CREATE SEQUENCE IF NOT EXISTS public.items_id_seq")

    # 2) 严格把 id 默认值设置为 nextval 序列（幂等：SET DEFAULT 覆盖或设定即可）
    op.execute(
        "ALTER TABLE public.items "
        "ALTER COLUMN id SET DEFAULT nextval('public.items_id_seq'::regclass)"
    )

    # 3) 绑定 OWNED BY，确保删列自动清理序列（不存在也不会报错）
    op.execute("ALTER SEQUENCE public.items_id_seq OWNED BY public.items.id")

    # 4) 对齐序列位置：取 MAX(id)+1 与当前序列 last_value 的较大者
    op.execute(
        """
        SELECT setval(
          'public.items_id_seq',
          GREATEST(
            COALESCE((SELECT MAX(id) FROM public.items), 0) + 1,
            COALESCE((SELECT last_value FROM public.items_id_seq), 1)
          ),
          false
        )
        """
    )

    # 5) 基线商品：SKU-001（没有唯一索引也可用 NOT EXISTS 方式幂等插入）
    op.execute(
        """
        INSERT INTO public.items (sku, name, unit)
        SELECT 'SKU-001', 'X猫粮', 'EA'
        WHERE NOT EXISTS (SELECT 1 FROM public.items WHERE sku='SKU-001')
        """
    )

    # 6) 再对齐一次（保证插入后序列正确）
    op.execute(
        """
        SELECT setval(
          'public.items_id_seq',
          COALESCE((SELECT MAX(id) FROM public.items), 0),
          true
        )
        """
    )


def downgrade():
    # 仅撤销默认值与归属，不删任何业务数据
    op.execute("ALTER TABLE public.items ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER SEQUENCE IF EXISTS public.items_id_seq OWNED BY NONE")
