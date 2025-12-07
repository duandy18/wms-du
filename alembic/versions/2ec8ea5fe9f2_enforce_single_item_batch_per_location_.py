"""
enforce single item+batch per location; auto-rebind on empty

Revision ID: 2ec8ea5fe9f2
Revises: 9905a16f8509
Create Date: 2025-11-10 14:06:15.502959
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "2ec8ea5fe9f2"
down_revision: Union[str, Sequence[str], None] = "9905a16f8509"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 在 locations 增加绑定列（可空）
    op.add_column("locations", sa.Column("current_item_id", sa.Integer(), nullable=True))
    op.add_column("locations", sa.Column("current_batch_id", sa.Integer(), nullable=True))

    op.execute("""
    ALTER TABLE locations
      ADD CONSTRAINT fk_locations_current_item
      FOREIGN KEY (current_item_id) REFERENCES items(id)
      ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
    ALTER TABLE locations
      ADD CONSTRAINT fk_locations_current_batch
      FOREIGN KEY (current_batch_id) REFERENCES batches(id)
      ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
    """)

    # 2) 历史体检：多商品/多批次 → 中止迁移
    op.execute("""
    DO $$
    DECLARE r RECORD;
    BEGIN
      FOR r IN
        SELECT location_id,
               COUNT(DISTINCT item_id)  AS di,
               COUNT(DISTINCT batch_id) AS db
          FROM stocks
         GROUP BY location_id
         HAVING COUNT(DISTINCT item_id) > 1 OR COUNT(DISTINCT batch_id) > 1
      LOOP
        RAISE EXCEPTION 'Migration aborted: location % has mixed items/batches (items=%, batches=%). Clean up first.',
          r.location_id, r.di, r.db;
      END LOOP;

      -- 单一商品/批次的库位做回填
      UPDATE locations l
         SET current_item_id  = s.item_id,
             current_batch_id = s.batch_id
        FROM (
          SELECT location_id,
                 MAX(item_id)  AS item_id,
                 MAX(batch_id) AS batch_id
            FROM stocks
           GROUP BY location_id
        ) s
       WHERE l.id = s.location_id
         AND (l.current_item_id IS NULL OR l.current_batch_id IS NULL);
    END$$;
    """)

    # 3) BEFORE INSERT ON stocks：绑定/校验/改绑（仅清空时允许改绑）
    op.execute("""
    CREATE OR REPLACE FUNCTION enforce_single_item_batch_per_location() RETURNS TRIGGER AS $$
    DECLARE loc_item int; loc_batch int; sum_qty numeric;
    BEGIN
      SELECT current_item_id, current_batch_id INTO loc_item, loc_batch
        FROM locations WHERE id = NEW.location_id;

      -- 未绑定：必须明确批次，然后绑定
      IF loc_item IS NULL OR loc_batch IS NULL THEN
        IF NEW.batch_id IS NULL THEN
          RAISE EXCEPTION 'mixed-batch rule: location % not bound yet; incoming batch_id is NULL', NEW.location_id;
        END IF;
        UPDATE locations
           SET current_item_id  = NEW.item_id,
               current_batch_id = NEW.batch_id
         WHERE id = NEW.location_id;
        RETURN NEW;
      END IF;

      -- 已绑定：不一致则仅在清空时允许改绑
      IF (NEW.item_id <> loc_item) OR (NEW.batch_id IS DISTINCT FROM loc_batch) THEN
        SELECT COALESCE(SUM(qty), 0) INTO sum_qty
          FROM stocks
         WHERE location_id = NEW.location_id;
        IF sum_qty <> 0 THEN
          RAISE EXCEPTION 'mixed-batch rule: location % bound to (item %, batch %), incoming (item %, batch %) while not empty',
            NEW.location_id, loc_item, loc_batch, NEW.item_id, NEW.batch_id;
        ELSE
          IF NEW.batch_id IS NULL THEN
            RAISE EXCEPTION 'mixed-batch rule: rebind requires non-NULL batch_id (location %)', NEW.location_id;
          END IF;
          UPDATE locations
             SET current_item_id  = NEW.item_id,
                 current_batch_id = NEW.batch_id
           WHERE id = NEW.location_id;
        END IF;
      END IF;

      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_enforce_single_item_batch_per_location ON stocks;
    CREATE TRIGGER trg_enforce_single_item_batch_per_location
      BEFORE INSERT ON stocks
      FOR EACH ROW
      EXECUTE FUNCTION enforce_single_item_batch_per_location();
    """)

    # 4) AFTER UPDATE/DELETE ON stocks：库位清空则自动解绑
    op.execute("""
    CREATE OR REPLACE FUNCTION auto_unbind_location_when_empty() RETURNS TRIGGER AS $$
    DECLARE sum_qty numeric; loc_id int;
    BEGIN
      loc_id := COALESCE(OLD.location_id, NEW.location_id);
      SELECT COALESCE(SUM(qty), 0) INTO sum_qty FROM stocks WHERE location_id = loc_id;
      IF sum_qty = 0 THEN
        UPDATE locations
           SET current_item_id = NULL,
               current_batch_id = NULL
         WHERE id = loc_id;
      END IF;
      RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_auto_unbind_location_when_empty ON stocks;
    CREATE TRIGGER trg_auto_unbind_location_when_empty
      AFTER UPDATE OR DELETE ON stocks
      FOR EACH STATEMENT
      EXECUTE FUNCTION auto_unbind_location_when_empty();
    """)

    # ⚠️ 5) 索引：改为异步后置提示（避免 "pending trigger events"）
    print(
        "\\n[NOTICE] 迁移完成，但索引将在下一事务中创建："
        "\\n  CREATE INDEX IF NOT EXISTS ix_locations_current_item  ON locations(current_item_id);"
        "\\n  CREATE INDEX IF NOT EXISTS ix_locations_current_batch ON locations(current_batch_id);\\n"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_auto_unbind_location_when_empty ON stocks;")
    op.execute("DROP FUNCTION IF EXISTS auto_unbind_location_when_empty();")
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_single_item_batch_per_location ON stocks;")
    op.execute("DROP FUNCTION IF EXISTS enforce_single_item_batch_per_location();")

    op.execute("ALTER TABLE locations DROP CONSTRAINT IF EXISTS fk_locations_current_item;")
    op.execute("ALTER TABLE locations DROP CONSTRAINT IF EXISTS fk_locations_current_batch;")

    op.drop_column("locations", "current_item_id")
    op.drop_column("locations", "current_batch_id")
