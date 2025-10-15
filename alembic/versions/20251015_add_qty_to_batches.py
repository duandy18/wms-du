"""add qty column to batches if missing (idempotent)

Revision ID: 20251015_add_qty_to_batches
Revises: 20251015_create_batches_if_missing
Create Date: 2025-10-15
"""

from alembic import op

revision = "20251015_add_qty_to_batches"
down_revision = "20251015_create_batches_if_missing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 若 batches 表存在且缺少 qty 列，则添加为 NOT NULL DEFAULT 0（幂等）
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.batches') IS NOT NULL THEN
            IF NOT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema='public'
                AND table_name='batches'
                AND column_name='qty'
            ) THEN
              ALTER TABLE public.batches
                ADD COLUMN qty INTEGER NOT NULL DEFAULT 0;
              -- 可选：去掉默认值，只保留 NOT NULL 约束（避免以后误用默认值）
              ALTER TABLE public.batches
                ALTER COLUMN qty DROP DEFAULT;
            END IF;
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # 通常不回滚；如需回退，可按需删除该列（但会影响已有数据）
    pass
