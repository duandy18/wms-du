"""batches: unify expiry calculation (CHECK + trigger fallback)

Revision ID: 20251101_batches_expiry_constraints
Revises: 20251101_v_scan_trace_view
Create Date: 2025-11-01 23:10:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20251101_batches_expiry_constraints"
down_revision = "20251101_v_scan_trace_view"
branch_labels = None
depends_on = None

# 说明：
# - 仅当 batches 存在 production_date/shelf_life_days/expire_at 三列时才启用校验与触发器
# - 触发器只在 expire_at 为 NULL 且另外两列均非空时，自动回填，不覆盖应用侧已算好的值

CHECK_NAME = "ck_batches_expire_ge_production"

CHECK_SQL = f"""
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name='batches' AND column_name='expire_at'
  ) AND EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='batches' AND column_name='production_date'
  ) THEN
    -- 若约束不存在则创建
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = '{CHECK_NAME}'
    ) THEN
      ALTER TABLE batches
      ADD CONSTRAINT {CHECK_NAME}
      CHECK (expire_at IS NULL OR production_date IS NULL OR expire_at >= production_date);
    END IF;
  END IF;
END
$$;
"""

# 轻触发器：仅在 expire_at 为空、且 production_date/shelf_life_days 存在且非空时自动计算
FN_SQL = r"""
CREATE OR REPLACE FUNCTION batches_fill_expire_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP IN ('INSERT','UPDATE') THEN
    IF NEW.expire_at IS NULL
       AND NEW.production_date IS NOT NULL
       AND NEW.shelf_life_days IS NOT NULL
    THEN
      IF NEW.shelf_life_days < 0 THEN
        RAISE EXCEPTION 'shelf_life_days must be >= 0';
      END IF;
      NEW.expire_at := NEW.production_date + (NEW.shelf_life_days || ' days')::interval;
      NEW.expire_at := date_trunc('day', NEW.expire_at)::date; -- 去时间分量
    END IF;
  END IF;
  RETURN NEW;
END
$$;
"""

TRIGGER_SQL = r"""
DO $$
BEGIN
  -- 三列都在时才挂触发器
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema='public' AND table_name='batches' AND column_name='expire_at')
     AND EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='batches' AND column_name='production_date')
     AND EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='batches' AND column_name='shelf_life_days')
  THEN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trg_batches_fill_expire_at') THEN
      CREATE TRIGGER trg_batches_fill_expire_at
      BEFORE INSERT OR UPDATE ON batches
      FOR EACH ROW
      EXECUTE FUNCTION batches_fill_expire_at();
    END IF;
  END IF;
END
$$;
"""

DROP_SQL = r"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='trg_batches_fill_expire_at') THEN
    DROP TRIGGER trg_batches_fill_expire_at ON batches;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname='batches_fill_expire_at') THEN
    DROP FUNCTION batches_fill_expire_at;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_batches_expire_ge_production') THEN
    ALTER TABLE batches DROP CONSTRAINT ck_batches_expire_ge_production;
  END IF;
END
$$;
"""

def upgrade():
    op.execute(CHECK_SQL)
    op.execute(FN_SQL)
    op.execute(TRIGGER_SQL)

def downgrade():
    op.execute(DROP_SQL)
