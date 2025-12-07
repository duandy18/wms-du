"""phase34: seed baseline (item=3003 wh=1 loc=900 NEAR qty=10)

Revision ID: p34_20251112_seed
Revises: 7f303f46e944
Create Date: 2025-11-12 16:59:28.877768
"""
from alembic import op
import sqlalchemy as sa  # noqa

# revision identifiers, used by Alembic.
revision = "p34_20251112_seed"
down_revision = "7f303f46e944"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Phase 3.4 baseline seed (idempotent):
      ITEM=3003, WH=1, LOC=900, BATCH=NEAR, qty=10
    - 仅在目标表存在时写入
    - 动态探测列存在性；只插当前库真实存在的列
    - 多次执行安全（基于 NOT EXISTS，而不是 ON CONFLICT）
    """
    ITEM_ID = 3003
    WH_ID = 1
    LOC_ID = 900
    BATCH_CODE = "NEAR"
    BASE_QTY = 10

    # 1) items：按常见必填列（sku/name 等）动态插入
    op.execute(f"""
    DO $$
    DECLARE
      tbl_exists boolean;
      cols text := '';
      vals text := '';
      sep  text := '';
      -- 依次尝试这些列；不存在就跳过
      want_cols text[] := ARRAY['id','sku','name','uom','unit','uom_code'];
      col text;
      has boolean;
    BEGIN
      SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='items'
      ) INTO tbl_exists;
      IF NOT tbl_exists THEN RETURN; END IF;

      FOREACH col IN ARRAY want_cols LOOP
        SELECT EXISTS (
          SELECT 1 FROM information_schema.columns
          WHERE table_schema='public' AND table_name='items' AND column_name=col
        ) INTO has;

        IF has THEN
          cols := cols || sep || col;
          IF col='id' THEN
            vals := vals || sep || {ITEM_ID};
          ELSIF col='sku' THEN
            vals := vals || sep || quote_literal('SKU-{ITEM_ID}');
          ELSIF col='name' THEN
            vals := vals || sep || quote_literal('Item-{ITEM_ID}');
          ELSE
            vals := vals || sep || quote_literal('PCS');
          END IF;
          sep := ', ';
        END IF;
      END LOOP;

      IF cols <> '' THEN
        EXECUTE format('INSERT INTO items (%s) VALUES (%s) ON CONFLICT (id) DO NOTHING', cols, vals);
      END IF;
    END$$;
    """)

    # 2) locations：插 LOC=900，常见列 warehouse_id/code/name
    op.execute(f"""
    DO $$
    DECLARE
      tbl_exists boolean;
      c_id boolean; c_wh boolean; c_code boolean; c_name boolean;
      cols text := ''; vals text := ''; sep text := '';
    BEGIN
      SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='locations'
      ) INTO tbl_exists;
      IF NOT tbl_exists THEN RETURN; END IF;

      SELECT
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='locations' AND column_name='id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='locations' AND column_name='warehouse_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='locations' AND column_name='code'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='locations' AND column_name='name')
      INTO c_id, c_wh, c_code, c_name;

      IF c_id THEN  cols := cols||sep||'id';            vals := vals||sep||{LOC_ID};           sep:=', '; END IF;
      IF c_wh THEN  cols := cols||sep||'warehouse_id';  vals := vals||sep||{WH_ID};            sep:=', '; END IF;
      IF c_code THEN cols := cols||sep||'code';         vals := vals||sep||quote_literal('LOC-{LOC_ID}'); sep:=', '; END IF;
      IF c_name THEN cols := cols||sep||'name';         vals := vals||sep||quote_literal('LOC-{LOC_ID}'); sep:=', '; END IF;

      IF cols <> '' THEN
        EXECUTE format('INSERT INTO locations (%s) VALUES (%s) ON CONFLICT (id) DO NOTHING', cols, vals);
      END IF;
    END$$;
    """)

    # 3) batches：按常见键 (item_id, warehouse_id, location_id, batch_code)
    #    但不再使用 ON CONFLICT，而是基于 NOT EXISTS 做幂等插入
    op.execute(f"""
    DO $$
    DECLARE
      tbl_exists boolean;
      c_item boolean; c_wh boolean; c_loc boolean; c_code boolean;
      cols text := ''; vals text := ''; sep text := '';
      where_clause text := ''; sep3 text := '';
    BEGIN
      SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='batches'
      ) INTO tbl_exists;
      IF NOT tbl_exists THEN RETURN; END IF;

      SELECT
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='batches' AND column_name='item_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='batches' AND column_name='warehouse_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='batches' AND column_name='location_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='batches' AND column_name='batch_code')
      INTO c_item, c_wh, c_loc, c_code;

      IF c_item THEN
        cols := cols||sep||'item_id';
        vals := vals||sep||{ITEM_ID};
        where_clause := where_clause||sep3||'item_id='||{ITEM_ID};
        sep:=', '; sep3:=' AND ';
      END IF;

      IF c_wh THEN
        cols := cols||sep||'warehouse_id';
        vals := vals||sep||{WH_ID};
        where_clause := where_clause||sep3||'warehouse_id='||{WH_ID};
        sep:=', '; sep3:=' AND ';
      END IF;

      IF c_loc THEN
        cols := cols||sep||'location_id';
        vals := vals||sep||{LOC_ID};
        where_clause := where_clause||sep3||'location_id='||{LOC_ID};
        sep:=', '; sep3:=' AND ';
      END IF;

      IF c_code THEN
        cols := cols||sep||'batch_code';
        vals := vals||sep||quote_literal('{BATCH_CODE}');
        where_clause := where_clause||sep3||'batch_code='||quote_literal('{BATCH_CODE}');
        sep:=', '; sep3:=' AND ';
      END IF;

      IF cols <> '' THEN
        IF where_clause = '' THEN
          -- 没有任何键列，就直接插一行（极端情况）
          EXECUTE format('INSERT INTO batches (%s) VALUES (%s)', cols, vals);
        ELSE
          -- 仅在不存在匹配行时插入
          EXECUTE format(
            'INSERT INTO batches (%s) SELECT %s WHERE NOT EXISTS (SELECT 1 FROM batches WHERE %s)',
            cols, vals, where_clause
          );
        END IF;
      END IF;
    END$$;
    """)

    # 4) stocks：删除后按基线重建 qty=10
    op.execute(f"""
    DO $$
    DECLARE
      tbl_exists boolean;
      has_item boolean; has_wh boolean; has_loc boolean; has_code boolean; has_qty boolean;
      del_sql text := 'DELETE FROM stocks WHERE 1=1';
      ins_cols text := ''; ins_vals text := ''; sep text := '';
    BEGIN
      SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='stocks'
      ) INTO tbl_exists;
      IF NOT tbl_exists THEN RETURN; END IF;

      SELECT
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='stocks' AND column_name='item_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='stocks' AND column_name='warehouse_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='stocks' AND column_name='location_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='stocks' AND column_name='batch_code'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='stocks' AND column_name='qty')
      INTO has_item, has_wh, has_loc, has_code, has_qty;

      IF has_item THEN del_sql := del_sql || ' AND item_id=' || {ITEM_ID}; END IF;
      IF has_wh   THEN del_sql := del_sql || ' AND warehouse_id=' || {WH_ID}; END IF;
      IF has_loc  THEN del_sql := del_sql || ' AND location_id=' || {LOC_ID}; END IF;
      IF has_code THEN del_sql := del_sql || ' AND batch_code=' || quote_literal('{BATCH_CODE}'); END IF;
      EXECUTE del_sql;

      IF has_item THEN ins_cols := ins_cols||sep||'item_id';     ins_vals := ins_vals||sep||{ITEM_ID};          sep:=', '; END IF;
      IF has_wh   THEN ins_cols := ins_cols||sep||'warehouse_id';ins_vals := ins_vals||sep||{WH_ID};            sep:=', '; END IF;
      IF has_loc  THEN ins_cols := ins_cols||sep||'location_id'; ins_vals := ins_vals||sep||{LOC_ID};           sep:=', '; END IF;
      IF has_code THEN ins_cols := ins_cols||sep||'batch_code';  ins_vals := ins_vals||sep||quote_literal('{BATCH_CODE}'); sep:=', '; END IF;
      IF has_qty  THEN ins_cols := ins_cols||sep||'qty';         ins_vals := ins_vals||sep||{BASE_QTY};         sep:=', '; END IF;

      IF ins_cols <> '' THEN
        EXECUTE format('INSERT INTO stocks (%s) VALUES (%s)', ins_cols, ins_vals);
      END IF;
    END$$;
    """)


def downgrade() -> None:
    """Remove Phase 3.4 seeded rows (safe if schema/columns exist)."""
    ITEM_ID = 3003
    WH_ID = 1
    LOC_ID = 900
    BATCH_CODE = "NEAR"

    # 删除 stocks
    op.execute(f"""
    DO $$
    DECLARE
      tbl_exists boolean;
      has_item boolean; has_wh boolean; has_loc boolean; has_code boolean;
      del_sql text := 'DELETE FROM stocks WHERE 1=1';
    BEGIN
      SELECT EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_schema='public' AND table_name='stocks')
      INTO tbl_exists;
      IF NOT tbl_exists THEN RETURN; END IF;

      SELECT
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='stocks' AND column_name='item_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='stocks' AND column_name='warehouse_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='stocks' AND column_name='location_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='stocks' AND column_name='batch_code')
      INTO has_item, has_wh, has_loc, has_code;

      IF has_item THEN del_sql := del_sql || ' AND item_id=' || {ITEM_ID}; END IF;
      IF has_wh   THEN del_sql := del_sql || ' AND warehouse_id=' || {WH_ID}; END IF;
      IF has_loc  THEN del_sql := del_sql || ' AND location_id=' || {LOC_ID}; END IF;
      IF has_code THEN del_sql := del_sql || ' AND batch_code=' || quote_literal('{BATCH_CODE}'); END IF;

      EXECUTE del_sql;
    END$$;
    """)

    # 删除 batches（不删 items/locations，避免误伤历史数据）
    op.execute(f"""
    DO $$
    DECLARE
      tbl_exists boolean;
      has_item boolean; has_wh boolean; has_loc boolean; has_code boolean;
      del_sql text := 'DELETE FROM batches WHERE 1=1';
    BEGIN
      SELECT EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_schema='public' AND table_name='batches')
      INTO tbl_exists;
      IF NOT tbl_exists THEN RETURN; END IF;

      SELECT
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='batches' AND column_name='item_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='batches' AND column_name='warehouse_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='batches' AND column_name='location_id'),
        EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='batches' AND column_name='batch_code')
      INTO has_item, has_wh, has_loc, has_code;

      IF has_item THEN del_sql := del_sql || ' AND item_id=' || {ITEM_ID}; END IF;
      IF has_wh   THEN del_sql := del_sql || ' AND warehouse_id=' || {WH_ID}; END IF;
      IF has_loc  THEN del_sql := del_sql || ' AND location_id=' || {LOC_ID}; END IF;
      IF has_code THEN del_sql := del_sql || ' AND batch_code=' || quote_literal('{BATCH_CODE}'); END IF;

      EXECUTE del_sql;
    END$$;
    """)
