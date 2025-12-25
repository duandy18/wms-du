"""warehouses_code_not_null_unique

Revision ID: e9c6712f47a6
Revises: 64ae43b2e55c
Create Date: 2025-12-13 11:26:10.453992

目标（Phase 3 延展）：
- warehouses.code 回填 + NOT NULL + UNIQUE
- code 作为“仓库坐标系稳定引用编码”，不得为空且必须唯一
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e9c6712f47a6"
down_revision: Union[str, Sequence[str], None] = "64ae43b2e55c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 回填 NULL / 空字符串 → WH-<id>
    op.execute(
        sa.text(
            """
            UPDATE warehouses
               SET code = 'WH-' || id::text
             WHERE code IS NULL OR btrim(code) = '';
            """
        )
    )

    # 2) 统一 trim（避免 ' WH1 ' 这种脏值影响唯一）
    op.execute(
        sa.text(
            """
            UPDATE warehouses
               SET code = btrim(code)
             WHERE code <> btrim(code);
            """
        )
    )

    # 3) 加 NOT NULL
    op.alter_column(
        "warehouses",
        "code",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    # 4) 加 UNIQUE 约束（如果已存在则跳过）
    #    注意：你库里历史上可能存在 unique=True 自动创建的 index/constraint，
    #    这里用 pg_constraint 定点判断，避免重复创建炸库。
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conname = 'uq_warehouses_code'
              ) THEN
                ALTER TABLE warehouses
                  ADD CONSTRAINT uq_warehouses_code UNIQUE (code);
              END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    # 回滚：先删 UNIQUE（若存在），再放开 NOT NULL
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conname = 'uq_warehouses_code'
              ) THEN
                ALTER TABLE warehouses
                  DROP CONSTRAINT uq_warehouses_code;
              END IF;
            END $$;
            """
        )
    )

    op.alter_column(
        "warehouses",
        "code",
        existing_type=sa.String(length=64),
        nullable=True,
    )
