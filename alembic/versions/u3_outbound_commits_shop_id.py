# alembic/versions/u3_outbound_commits_shop_id.py
from alembic import op
import sqlalchemy as sa

revision = "u3_outbound_commits_shop_id"
down_revision = "u2_event_error_log_message_text"  # 与现有链路保持一致
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 采用 PG 的元数据判断，保证幂等
    op.execute(
        """
        DO $$
        BEGIN
          -- 1) 列不存在才添加（临时默认值以满足 NOT NULL，随后移除默认）
          IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='outbound_commits'
              AND column_name='shop_id'
          ) THEN
            ALTER TABLE public.outbound_commits
              ADD COLUMN shop_id VARCHAR(64) NOT NULL DEFAULT '';
            ALTER TABLE public.outbound_commits
              ALTER COLUMN shop_id DROP DEFAULT;
          END IF;

          -- 2) 旧索引存在则删除（命名可能与历史不同，按需保留此清理）
          IF EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public' AND indexname='ux_outbound_commits_3cols'
          ) THEN
            DROP INDEX public.ux_outbound_commits_3cols;
          END IF;

          -- 3) 新唯一索引（平台 × 店铺 × 单号 × 状态）—— 不存在才创建
          IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public' AND indexname='ux_outbound_commits_4cols'
          ) THEN
            CREATE UNIQUE INDEX ux_outbound_commits_4cols
              ON public.outbound_commits(platform, shop_id, ref, state);
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # 幂等回退：索引/列存在才删除
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public' AND indexname='ux_outbound_commits_4cols'
          ) THEN
            DROP INDEX public.ux_outbound_commits_4cols;
          END IF;

          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='outbound_commits'
              AND column_name='shop_id'
          ) THEN
            ALTER TABLE public.outbound_commits DROP COLUMN shop_id;
          END IF;
        END$$;
        """
    )
