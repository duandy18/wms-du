"""bootstrap stage location (id=0) + ensure identity/default for items/locations

Revision ID: 20251106_bootstrap_stage_location_and_ids
Revises: 20251105_add_unique_on_stores_platform_name
Create Date: 2025-11-06
"""

from __future__ import annotations

from alembic import op


revision = "20251106_bootstrap_stage_location_and_ids"
down_revision = "20251105_add_unique_on_stores_platform_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
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

      -- 对齐序列（避免下次插入冲突）：确保序列值至少为 1
      PERFORM setval(
        pg_get_serial_sequence('public.items','id'),
        GREATEST(COALESCE((SELECT MAX(id) FROM public.items), 1), 1),
        true
      );

      PERFORM setval(
        pg_get_serial_sequence('public.locations','id'),
        GREATEST(COALESCE((SELECT MAX(id) FROM public.locations), 1), 1),
        true
      );
    END $$;
    """
    )


def downgrade() -> None:
    # 保守处理：不回收 0 号 STAGE、不删示例 items/warehouses，只是留存
    # 若未来有严格需求，可以在单独 migration 中清理这些 bootstrap 数据
    pass
