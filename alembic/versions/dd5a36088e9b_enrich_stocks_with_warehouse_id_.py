"""enrich stocks with warehouse_id; converge uniques/FKs; enforce location↔warehouse consistency

Revision ID: dd5a36088e9b
Revises: 8ccea664a61e
Create Date: 2025-11-10 08:45:00.837175
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "dd5a36088e9b"
down_revision: Union[str, Sequence[str], None] = "8ccea664a61e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0) 新增 warehouse_id（先允许 NULL）
    op.add_column("stocks", sa.Column("warehouse_id", sa.Integer(), nullable=True))

    # 1) 回填：优先 batches，其次 locations
    op.execute("""
    UPDATE stocks s
       SET warehouse_id = b.warehouse_id
      FROM batches b
     WHERE s.batch_id = b.id
       AND s.warehouse_id IS NULL;
    UPDATE stocks s
       SET warehouse_id = l.warehouse_id
      FROM locations l
     WHERE s.location_id = l.id
       AND s.warehouse_id IS NULL;
    """)

    # 2) 设 NOT NULL + FK(stocks.warehouse_id → warehouses.id)
    op.alter_column("stocks", "warehouse_id", nullable=False)
    op.create_foreign_key(
        "fk_stocks_warehouse",
        "stocks", "warehouses",
        ["warehouse_id"], ["id"],
        ondelete="RESTRICT",
    )

    # 3) 收束重复外键（item/location/batch）
    op.execute("""
    DO $$
    BEGIN
      -- item/location 只保留命名的 fk_stocks_item / fk_stocks_location
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='stocks_item_id_fkey') THEN
        ALTER TABLE stocks DROP CONSTRAINT stocks_item_id_fkey;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='stocks_location_id_fkey') THEN
        ALTER TABLE stocks DROP CONSTRAINT stocks_location_id_fkey;
      END IF;

      -- 批次：删除其它同列重复 FK，统一成可延迟 + 置空删除
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
    END$$;
    """)

    # 4) 重建唯一约束/索引（删除旧的/冗余；创建新的“含仓”唯一）
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_stocks_item_loc_batch') THEN
        ALTER TABLE stocks DROP CONSTRAINT uq_stocks_item_loc_batch;
      END IF;
      IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='uq_stocks_withbatch' AND n.nspname=current_schema()
      ) THEN
        DROP INDEX uq_stocks_withbatch;
      END IF;
      IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='uq_stocks_nobatch' AND n.nspname=current_schema()
      ) THEN
        DROP INDEX uq_stocks_nobatch;
      END IF;
    END$$;
    """)

    op.execute("""
    ALTER TABLE stocks
      ADD CONSTRAINT uq_stocks_item_wh_loc_batch
      UNIQUE (item_id, warehouse_id, location_id, batch_id);

    CREATE UNIQUE INDEX uq_stocks_nobatch_wh
      ON stocks (item_id, warehouse_id, location_id)
      WHERE batch_id IS NULL;
    """)

    # 5) 触发器：保证 stocks.warehouse_id 与 locations.warehouse_id 一致
    op.execute("""
    CREATE OR REPLACE FUNCTION trg_stocks_sync_wh() RETURNS TRIGGER AS $$
    DECLARE v_wh integer;
    BEGIN
      SELECT warehouse_id INTO v_wh FROM locations WHERE id = NEW.location_id;
      IF v_wh IS NULL THEN
        RAISE EXCEPTION 'locations(%) has no warehouse_id', NEW.location_id;
      END IF;

      IF NEW.warehouse_id IS NULL THEN
        NEW.warehouse_id := v_wh;
      ELSIF NEW.warehouse_id <> v_wh THEN
        NEW.warehouse_id := v_wh; -- 自动对齐（也可选择抛错）
      END IF;

      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS stocks_sync_wh_iu ON stocks;
    CREATE TRIGGER stocks_sync_wh_iu
      BEFORE INSERT OR UPDATE OF location_id, warehouse_id ON stocks
      FOR EACH ROW EXECUTE FUNCTION trg_stocks_sync_wh();
    """)

    # 6) 建议查询索引（若无则建）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='idx_stocks_item_wh' AND n.nspname=current_schema()
      ) THEN
        CREATE INDEX idx_stocks_item_wh ON stocks(item_id, warehouse_id);
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='idx_stocks_loc' AND n.nspname=current_schema()
      ) THEN
        CREATE INDEX idx_stocks_loc ON stocks(location_id);
      END IF;
    END$$;
    """)


def downgrade() -> None:
    # 触发器回滚
    op.execute("DROP TRIGGER IF EXISTS stocks_sync_wh_iu ON stocks;")
    op.execute("DROP FUNCTION IF EXISTS trg_stocks_sync_wh();")

    # 唯一/索引回滚
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_stocks_item_wh_loc_batch') THEN
        ALTER TABLE stocks DROP CONSTRAINT uq_stocks_item_wh_loc_batch;
      END IF;
      DROP INDEX IF EXISTS uq_stocks_nobatch_wh;

      -- 恢复历史唯一（不推荐，但为对称）
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_stocks_item_loc_batch') THEN
        ALTER TABLE stocks
          ADD CONSTRAINT uq_stocks_item_loc_batch UNIQUE (item_id, location_id, batch_id);
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='uq_stocks_nobatch' AND n.nspname=current_schema()
      ) THEN
        CREATE UNIQUE INDEX uq_stocks_nobatch
          ON stocks (item_id, location_id) WHERE batch_id IS NULL;
      END IF;
    END$$;
    """)

    # 批次 FK 回滚（保守）
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stocks_batch_id') THEN
        ALTER TABLE stocks DROP CONSTRAINT fk_stocks_batch_id;
      END IF;
      ALTER TABLE stocks
        ADD CONSTRAINT stocks_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES batches(id);
    END$$;
    """)

    # 仓 FK 回滚 + 删除列
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS fk_stocks_warehouse;")
    op.drop_column("stocks", "warehouse_id")
