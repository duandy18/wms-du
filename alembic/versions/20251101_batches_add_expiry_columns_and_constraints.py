"""batches: add expiry columns + CHECK + trigger (idempotent)

Revision ID: 20251101_batches_add_expiry_columns_and_constraints
Revises: 20251101_v_scan_trace_view
Create Date: 2025-11-01 23:40:00
"""

from alembic import op

revision = "20251101_batches_add_expiry_columns_and_constraints"
down_revision = "20251101_v_scan_trace_view"
branch_labels = None
depends_on = None

CHECK_NAME = "ck_batches_expire_ge_production"

ADD_COLS_SQL = r"""
ALTER TABLE batches
  ADD COLUMN IF NOT EXISTS production_date DATE,
  ADD COLUMN IF NOT EXISTS shelf_life_days INTEGER,
  ADD COLUMN IF NOT EXISTS expire_at DATE;
"""

CHECK_SQL = f"""
DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1 FROM pg_constraint WHERE conname = '{CHECK_NAME}'
  ) THEN
    ALTER TABLE batches
      ADD CONSTRAINT {CHECK_NAME}
      CHECK (
        -- 只在 production_date 与 expire_at 同时非空时校验大小关系
        (production_date IS NULL OR expire_at IS NULL)
        OR (expire_at >= production_date)
      );
  END IF;
END
$$;
"""

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
      NEW.expire_at := (NEW.production_date + (NEW.shelf_life_days || ' days')::interval)::date;
    END IF;
  END IF;
  RETURN NEW;
END
$$;
"""

TRIGGER_SQL = r"""
DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1 FROM pg_trigger WHERE tgname='trg_batches_fill_expire_at'
  ) THEN
    CREATE TRIGGER trg_batches_fill_expire_at
    BEFORE INSERT OR UPDATE ON batches
    FOR EACH ROW
    EXECUTE FUNCTION batches_fill_expire_at();
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
    op.execute(ADD_COLS_SQL)
    op.execute(CHECK_SQL)
    op.execute(FN_SQL)
    op.execute(TRIGGER_SQL)


def downgrade():
    op.execute(DROP_SQL)
    # 列为兼容历史不自动回滚（避免误删已有数据列）
