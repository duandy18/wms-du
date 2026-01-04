"""v2: add FK batches.item_id -> items(id) final

Revision ID: b1a483b58d1e
Revises: 3f3e743a59af
Create Date: 2025-11-11 22:12:18.911341
"""
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1a483b58d1e"
down_revision: str | None = "3f3e743a59af"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    创建 batches.item_id -> items(id) 外键（先 NOT VALID，再尝试 VALIDATE）。
    - 幂等：若已存在同名约束，则跳过。
    """
    # 1) 如果不存在，则以 NOT VALID 创建 FK（避免历史孤儿阻塞迁移）
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM   pg_constraint c
            WHERE  c.conname = 'fk_batches_item'
              AND  c.conrelid = 'public.batches'::regclass
          ) THEN
            ALTER TABLE public.batches
              ADD CONSTRAINT fk_batches_item
              FOREIGN KEY (item_id) REFERENCES public.items(id) NOT VALID;
          END IF;
        END$$;
        """
    )

    # 2) 尝试验证（有孤儿会报错；捕获异常，保持 NOT VALID，不影响迁移通过）
    op.execute(
        """
        DO $$
        BEGIN
          BEGIN
            ALTER TABLE public.batches VALIDATE CONSTRAINT fk_batches_item;
          EXCEPTION WHEN others THEN
            -- 留在 NOT VALID 状态，后续清理孤儿后可手动 VALIDATE
            NULL;
          END;
        END$$;
        """
    )


def downgrade() -> None:
    """回滚：删除该外键（若存在）"""
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM   pg_constraint c
            WHERE  c.conname = 'fk_batches_item'
              AND  c.conrelid = 'public.batches'::regclass
          ) THEN
            ALTER TABLE public.batches DROP CONSTRAINT fk_batches_item;
          END IF;
        END$$;
        """
    )
