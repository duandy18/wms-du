"""fix stock_ledger trinity (created_at, types, FKs) with auto view detach/restore

Revision ID: 80d901c60739
Revises: 567351fff27e
Create Date: 2025-11-10 01:31:21.714806
"""
from alembic import op
import sqlalchemy as sa

revision: str = "80d901c60739"
down_revision: str | None = "567351fff27e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0) 保存并卸载当前 schema 中所有“引用 stock_ledger.(reason|delta|after_qty)”的视图
    op.execute("""
    DO $$
    DECLARE
      r record;
      vdef text;
      vtxt text;
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_tables WHERE schemaname=current_schema() AND tablename='_tmp_saved_views'
      ) THEN
        CREATE TEMP TABLE _tmp_saved_views(name text primary key, ddl text) ON COMMIT DROP;
      END IF;

      FOR r IN
        SELECT c.oid, c.relname AS view_name
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'v' AND n.nspname = current_schema()
      LOOP
        vtxt := lower(pg_get_viewdef(r.oid, TRUE));
        IF position('stock_ledger' IN vtxt) > 0
           AND (
                position('reason'     IN vtxt) > 0 OR
                position('delta'      IN vtxt) > 0 OR
                position('after_qty'  IN vtxt) > 0
               )
        THEN
          vdef := 'CREATE OR REPLACE VIEW ' || quote_ident(r.view_name) || ' AS ' || pg_get_viewdef(r.oid, TRUE);
          INSERT INTO _tmp_saved_views(name, ddl)
               VALUES (r.view_name, vdef)
          ON CONFLICT (name) DO UPDATE SET ddl = EXCLUDED.ddl;
          EXECUTE 'DROP VIEW ' || quote_ident(r.view_name);
        END IF;
      END LOOP;
    END$$;
    """)

    # 1) created_at 列：timestamptz NOT NULL DEFAULT now()
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name   = 'stock_ledger'
           AND column_name  = 'created_at'
      ) THEN
        ALTER TABLE stock_ledger
          ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
      END IF;
    END$$;
    """)

    # 2) reason 长度改为 varchar(32)
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
          FROM pg_attrdef d
          JOIN pg_class c ON c.oid=d.adrelid
          JOIN pg_attribute a ON a.attrelid=d.adrelid AND a.attnum=d.adnum
          JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='stock_ledger' AND a.attname='reason' AND n.nspname=current_schema()
      ) THEN
        ALTER TABLE stock_ledger ALTER COLUMN reason DROP DEFAULT;
      END IF;

      ALTER TABLE stock_ledger
        ALTER COLUMN reason TYPE varchar(32) USING substring(reason, 1, 32);
    END$$;
    """)

    # 3) delta / after_qty 改为 double precision
    op.execute("""
    DO $$
    BEGIN
      ALTER TABLE stock_ledger
        ALTER COLUMN delta     TYPE double precision USING delta::double precision,
        ALTER COLUMN after_qty TYPE double precision USING after_qty::double precision;
    END$$;
    """)

    # 4) 外键补齐（location/item/stock）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stock_ledger_location_id') THEN
        ALTER TABLE stock_ledger
          ADD CONSTRAINT fk_stock_ledger_location_id
          FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE RESTRICT;
      END IF;

      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stock_ledger_item_id') THEN
        ALTER TABLE stock_ledger
          ADD CONSTRAINT fk_stock_ledger_item_id
          FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE RESTRICT;
      END IF;

      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stock_ledger_stock_id') THEN
        ALTER TABLE stock_ledger
          ADD CONSTRAINT fk_stock_ledger_stock_id
          FOREIGN KEY (stock_id) REFERENCES stocks(id) ON DELETE CASCADE;
      END IF;
    END$$;
    """)

    # 5) 还原刚才卸载的视图
    op.execute("""
    DO $$
    DECLARE
      r record;
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_schema=current_schema() AND table_name='_tmp_saved_views'
      ) THEN
        FOR r IN SELECT name, ddl FROM _tmp_saved_views ORDER BY name LOOP
          EXECUTE r.ddl;
        END LOOP;
      END IF;
    END$$;
    """)


def downgrade() -> None:
    # 回滚外键
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stock_ledger_stock_id') THEN
        ALTER TABLE stock_ledger DROP CONSTRAINT fk_stock_ledger_stock_id;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stock_ledger_item_id') THEN
        ALTER TABLE stock_ledger DROP CONSTRAINT fk_stock_ledger_item_id;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stock_ledger_location_id') THEN
        ALTER TABLE stock_ledger DROP CONSTRAINT fk_stock_ledger_location_id;
      END IF;
    END$$;
    """)

    # 回滚类型（保守）
    op.execute("""
    DO $$
    BEGIN
      ALTER TABLE stock_ledger
        ALTER COLUMN after_qty TYPE numeric(18,6) USING after_qty::numeric(18,6),
        ALTER COLUMN delta     TYPE numeric(18,6) USING delta::numeric(18,6);
      ALTER TABLE stock_ledger
        ALTER COLUMN reason    TYPE varchar(64) USING reason::varchar(64);
    END$$;
    """)

    # 回收 created_at
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name   = 'stock_ledger'
           AND column_name  = 'created_at'
      ) THEN
        ALTER TABLE stock_ledger DROP COLUMN created_at;
      END IF;
    END$$;
    """)
