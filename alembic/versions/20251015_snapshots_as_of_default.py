"""ensure stock_snapshots.as_of_ts has default for NOT NULL inserts"""

from alembic import op

revision = "20251015_snapshots_as_of_default"
down_revision = "20251015_fix_stock_snapshots_snapshot_date"  # 按你的最新修订填
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
          has_table boolean;
          has_col   boolean;
          has_default boolean;
        BEGIN
          has_table := to_regclass('public.stock_snapshots') IS NOT NULL;

          IF has_table THEN
            SELECT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='stock_snapshots'
                AND column_name='as_of_ts'
            ) INTO has_col;

            IF has_col THEN
              SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='stock_snapshots'
                  AND column_name='as_of_ts'
                  AND column_default IS NOT NULL
              ) INTO has_default;

              IF NOT has_default THEN
                ALTER TABLE public.stock_snapshots
                  ALTER COLUMN as_of_ts SET DEFAULT CURRENT_TIMESTAMP;
                -- 可选，保持 NOT NULL 但去掉默认，避免以后误用默认值
                -- ALTER TABLE public.stock_snapshots
                --   ALTER COLUMN as_of_ts DROP DEFAULT;
              END IF;
            END IF;
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    pass
