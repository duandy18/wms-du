"""drop spec_family from items

Revision ID: a65a60c9971b
Revises: d881ff90dc90
Create Date: 2025-12-12 19:34:15.872224
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a65a60c9971b"
down_revision: Union[str, Sequence[str], None] = "d881ff90dc90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    物理删除 items.spec_family 列（以及其索引，如存在）。

    设计原则：
    - 使用 IF EXISTS 保护，避免环境差异导致迁移失败
    - 先删索引，再删列
    """

    # 1) 删除索引（如果存在）
    # 之前 models/item.py 中对 spec_family 设置了 index=True
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_indexes
             WHERE schemaname = 'public'
               AND indexname = 'ix_items_spec_family'
          ) THEN
            DROP INDEX public.ix_items_spec_family;
          END IF;
        END
        $$;
        """
    )

    # 2) 删除列（如果存在）
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'items'
               AND column_name = 'spec_family'
          ) THEN
            ALTER TABLE public.items DROP COLUMN spec_family;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """
    回滚：重新添加 spec_family 列（仅恢复 schema，不恢复历史语义）。

    注意：
    - 默认值设为 'GENERAL'
    - 不尝试恢复历史数据，仅保证 downgrade 可执行
    """

    # 1) 恢复列（如果不存在）
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'items'
               AND column_name = 'spec_family'
          ) THEN
            ALTER TABLE public.items
              ADD COLUMN spec_family VARCHAR(32) NOT NULL DEFAULT 'GENERAL';
          END IF;
        END
        $$;
        """
    )

    # 2) 恢复索引（如果不存在）
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_indexes
             WHERE schemaname = 'public'
               AND indexname = 'ix_items_spec_family'
          ) THEN
            CREATE INDEX ix_items_spec_family ON public.items (spec_family);
          END IF;
        END
        $$;
        """
    )
