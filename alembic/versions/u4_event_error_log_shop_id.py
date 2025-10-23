# alembic/versions/u4_event_error_log_shop_id.py
from alembic import op
import sqlalchemy as sa

revision = "u4_event_error_log_shop_id"
down_revision = "u3_outbound_commits_shop_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 幂等添加列：仅当 event_error_log.shop_id 不存在时才添加
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='event_error_log'
              AND column_name='shop_id'
          ) THEN
            ALTER TABLE public.event_error_log
              ADD COLUMN shop_id VARCHAR(64);
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # 幂等回退：仅当列存在时才删除
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='event_error_log'
              AND column_name='shop_id'
          ) THEN
            ALTER TABLE public.event_error_log
              DROP COLUMN shop_id;
          END IF;
        END$$;
        """
    )
