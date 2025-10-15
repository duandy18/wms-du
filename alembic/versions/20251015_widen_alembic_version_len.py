# alembic/versions/20251015_widen_alembic_version_len.py
from alembic import op

revision = "20251015_widen_alembic_version_len"
down_revision = "20251014_fix_uniques_for_stocks_batches"


def upgrade():
    op.execute(
        """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'alembic_version'
          AND column_name = 'version_num'
          AND character_maximum_length IS NOT NULL
          AND character_maximum_length < 128
      ) THEN
        ALTER TABLE public.alembic_version
          ALTER COLUMN version_num TYPE VARCHAR(255);
      END IF;
    END$$;
    """
    )


def downgrade():
    pass  # 通常不回收
