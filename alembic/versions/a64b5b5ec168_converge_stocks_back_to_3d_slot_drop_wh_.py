"""converge stocks back to 3D slot; drop wh column and redundant FKs/uniques; keep compat name

Revision ID: a64b5b5ec168
Revises: 38d1587990e0
Create Date: 2025-11-10 09:19:10.465443
"""
from typing import Sequence, Union
from alembic import op

revision: str = "a64b5b5ec168"
down_revision: Union[str, Sequence[str], None] = "38d1587990e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0) 若存在 warehouse_id（我们回到三维槽位）→ 幂等删除
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema() AND table_name='stocks' AND column_name='warehouse_id'
      ) THEN
        -- 删触发器与函数
        DROP TRIGGER IF EXISTS stocks_sync_wh_iu ON stocks;
        IF EXISTS (
          SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE p.proname='trg_stocks_sync_wh' AND n.nspname=current_schema()
        ) THEN
          DROP FUNCTION trg_stocks_sync_wh();
        END IF;

        -- 删 wh 外键
        IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stocks_warehouse') THEN
          ALTER TABLE stocks DROP CONSTRAINT fk_stocks_warehouse;
        END IF;

        -- 删 wh 列
        ALTER TABLE stocks DROP COLUMN warehouse_id;
      END IF;
    END$$;
    """)

    # 1) 收束批次/重复外键（保留置空删除 + 可延迟的批次外键）
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stocks_batch') THEN
        ALTER TABLE stocks DROP CONSTRAINT fk_stocks_batch;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='stocks_batch_id_fkey') THEN
        ALTER TABLE stocks DROP CONSTRAINT stocks_batch_id_fkey;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stocks_batch_id') THEN
        ALTER TABLE stocks DROP CONSTRAINT fk_stocks_batch_id;
      END IF;

      ALTER TABLE stocks
        ADD CONSTRAINT fk_stocks_batch_id
        FOREIGN KEY (batch_id) REFERENCES batches(id)
        ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

      -- 去掉重复的 item/location 外键（保留命名的 fk_stocks_item / fk_stocks_location）
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='stocks_item_id_fkey') THEN
        ALTER TABLE stocks DROP CONSTRAINT stocks_item_id_fkey;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='stocks_location_id_fkey') THEN
        ALTER TABLE stocks DROP CONSTRAINT stocks_location_id_fkey;
      END IF;
    END$$;
    """)

    # 2) 统一唯一约束/索引，保持与主程序使用的名字一致
    op.execute("""
    DO $$
    BEGIN
      -- 若存在含 wh 名字的约束，改回兼容名
      IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname='uq_stocks_item_wh_loc_batch' AND conrelid='stocks'::regclass
      ) THEN
        ALTER TABLE stocks
          RENAME CONSTRAINT uq_stocks_item_wh_loc_batch
          TO uq_stocks_item_loc_batch;
      END IF;

      -- 删除可能存在的 'withbatch' 冗余唯一
      IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='uq_stocks_withbatch' AND n.nspname=current_schema()
      ) THEN
        DROP INDEX uq_stocks_withbatch;
      END IF;

      -- 删除按 wh 的 partial unique
      IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='uq_stocks_nobatch_wh' AND n.nspname=current_schema()
      ) THEN
        DROP INDEX uq_stocks_nobatch_wh;
      END IF;

      -- 创建/确保三维唯一（兼容名）
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname='uq_stocks_item_loc_batch' AND conrelid='stocks'::regclass
      ) THEN
        ALTER TABLE stocks
          ADD CONSTRAINT uq_stocks_item_loc_batch
          UNIQUE (item_id, location_id, batch_id);
      END IF;

      -- 确保无批次 partial unique 存在
      IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='uq_stocks_nobatch' AND n.nspname=current_schema()
      ) THEN
        CREATE UNIQUE INDEX uq_stocks_nobatch
          ON stocks (item_id, location_id) WHERE batch_id IS NULL;
      END IF;
    END$$;
    """)

    # 3) 清理按 wh 的建议索引（若曾建过）
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='idx_stocks_item_wh' AND n.nspname=current_schema()
      ) THEN
        DROP INDEX idx_stocks_item_wh;
      END IF;
    END$$;
    """)


def downgrade() -> None:
    # 回滚时不自动恢复 warehouse_id，若确需可在此处补回
    # 仅恢复曾删除的按 wh 的 partial unique（为了对称）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='uq_stocks_nobatch_wh' AND n.nspname=current_schema()
      ) THEN
        -- 仅示例；若无 warehouse_id 列，这一段保留无效（按需修改）
        CREATE UNIQUE INDEX uq_stocks_nobatch_wh
          ON stocks (item_id, warehouse_id, location_id) WHERE batch_id IS NULL;
      END IF;
    END$$;
    """)
