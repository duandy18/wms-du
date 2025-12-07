"""bootstrap stage location (id=0) + ensure identity/default for items/locations

Revision ID: 20251106_bootstrap_stage_location_and_ids
Revises: 20251105_add_unique_on_stores_platform_name
Create Date: 2025-11-06 16:20:00+08
"""

from alembic import op

revision = "20251106_bootstrap_stage_location_and_ids"
down_revision = "20251105_add_unique_on_stores_platform_name"
branch_labels = None
depends_on = None


def upgrade():
    # 1) items.id & locations.id → 自增（已有则跳过），并确保 OWNED BY + setval
    op.execute("""
    DO $$
    BEGIN
      -- items.id
      BEGIN
        ALTER TABLE public.items ALTER COLUMN id DROP IDENTITY IF EXISTS;
      EXCEPTION WHEN undefined_table THEN
        -- 没有 items 表就不处理
        RETURN;
      WHEN others THEN NULL;
      END;

      -- 如果没有序列，则创建；已有则沿用
      IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind='S' AND n.nspname='public' AND c.relname='items_id_seq'
      ) THEN
        CREATE SEQUENCE public.items_id_seq;
      END IF;

      -- 绑定默认值
      BEGIN
        ALTER TABLE public.items ALTER COLUMN id SET DEFAULT nextval('public.items_id_seq'::regclass);
      EXCEPTION WHEN others THEN NULL;
      END;

      -- 归属
      ALTER SEQUENCE public.items_id_seq OWNED BY public.items.id;

      -- 对齐序列
      PERFORM setval('public.items_id_seq',
        COALESCE((SELECT GREATEST(MAX(id),1) FROM public.items),1), true);

      -- locations.id
      BEGIN
        ALTER TABLE public.locations ALTER COLUMN id DROP IDENTITY IF EXISTS;
      EXCEPTION WHEN undefined_table THEN
        RETURN;
      WHEN others THEN NULL;
      END;

      IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind='S' AND n.nspname='public' AND c.relname='locations_id_seq'
      ) THEN
        CREATE SEQUENCE public.locations_id_seq;
      END IF;

      BEGIN
        ALTER TABLE public.locations ALTER COLUMN id SET DEFAULT nextval('public.locations_id_seq'::regclass);
      EXCEPTION WHEN others THEN NULL;
      END;

      ALTER SEQUENCE public.locations_id_seq OWNED BY public.locations.id;

      PERFORM setval('public.locations_id_seq',
        COALESCE((SELECT GREATEST(MAX(id),1) FROM public.locations),1), true);
    END $$;
    """)

    # 2) 基线：仓库、暂存位(id=0)、演示 SKU
    op.execute("""
    DO $$
    BEGIN
      -- 仓库基线：若库表为空，插入 id=1
      IF NOT EXISTS (SELECT 1 FROM public.warehouses) THEN
        INSERT INTO public.warehouses(id, name) VALUES (1,'WH-DEFAULT')
        ON CONFLICT (id) DO NOTHING;
      END IF;

      -- 暂存位：id=0（幂等）
      IF NOT EXISTS (SELECT 1 FROM public.locations WHERE id=0) THEN
        -- 选择一个仓库作为归属（优先 id=1，否则任意一个）
        INSERT INTO public.locations(id, name, code, warehouse_id)
        VALUES (0, 'STAGE', 'STAGE', COALESCE(
          (SELECT 1 WHERE EXISTS (SELECT 1 FROM public.warehouses WHERE id=1)),
          (SELECT id FROM public.warehouses LIMIT 1)
        ));
      END IF;

      -- 演示 SKU：id=1（幂等，方便 /scan 使用 sku='SKU-001' 或 item_id=1）
      IF NOT EXISTS (SELECT 1 FROM public.items WHERE id=1) THEN
        INSERT INTO public.items(id, sku, name, unit)
        VALUES (1, 'SKU-001', 'X猫粮', 'EA')
        ON CONFLICT (id) DO NOTHING;
      END IF;

      -- 对齐序列（避免下次插入冲突）
      PERFORM setval(pg_get_serial_sequence('public.items','id'),
                     COALESCE((SELECT MAX(id) FROM public.items), 0), true);
      PERFORM setval(pg_get_serial_sequence('public.locations','id'),
                     COALESCE((SELECT MAX(id) FROM public.locations), 0), true);
    END $$;
    """)


def downgrade():
    # 回滚：只撤销“默认值/序列归属”，不硬删真实数据（仓库/暂存位/演示 SKU）
    op.execute("""
    DO $$
    BEGIN
      -- items
      BEGIN
        ALTER TABLE public.items ALTER COLUMN id DROP DEFAULT;
      EXCEPTION WHEN others THEN NULL; END;
      BEGIN
        ALTER SEQUENCE public.items_id_seq OWNED BY NONE;
      EXCEPTION WHEN undefined_table THEN NULL; WHEN others THEN NULL; END;

      -- locations
      BEGIN
        ALTER TABLE public.locations ALTER COLUMN id DROP DEFAULT;
      EXCEPTION WHEN others THEN NULL; END;
      BEGIN
        ALTER SEQUENCE public.locations_id_seq OWNED BY NONE;
      EXCEPTION WHEN undefined_table THEN NULL; WHEN others THEN NULL; END;
    END $$;
    """)
