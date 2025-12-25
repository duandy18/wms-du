"""add has_shelf_life to items

Revision ID: 7b5b0d8f53e2
Revises: a65a60c9971b
Create Date: 2025-12-12 22:27:46.995655
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7b5b0d8f53e2"
down_revision: Union[str, Sequence[str], None] = "a65a60c9971b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 增加列：has_shelf_life（事实开关）
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'items'
               AND column_name = 'has_shelf_life'
          ) THEN
            ALTER TABLE public.items
              ADD COLUMN has_shelf_life BOOLEAN NOT NULL DEFAULT false;
          END IF;
        END
        $$;
        """
    )

    # 2) 回填：历史上只要配置过 shelf_life_value/unit，就认为需要有效期管理
    op.execute(
        """
        UPDATE public.items
           SET has_shelf_life = true
         WHERE shelf_life_value IS NOT NULL
           AND shelf_life_unit IS NOT NULL
           AND TRIM(shelf_life_unit) <> '';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'items'
               AND column_name = 'has_shelf_life'
          ) THEN
            ALTER TABLE public.items DROP COLUMN has_shelf_life;
          END IF;
        END
        $$;
        """
    )
