"""pol simplify locator check constraints (not null)

Phase N+4 cleanup:
- locator_kind / locator_value 已是 NOT NULL
- 移除 CHECK 里的历史 “IS NULL OR …” 冗余分支
- 保持约束名不变，仅收敛表达式，避免语义歧义

Revision ID: 94cd680e8b72
Revises: 6f3449b2ca0b
Create Date: 2026-02-10 12:44:54.877435
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "94cd680e8b72"
down_revision: Union[str, Sequence[str], None] = "6f3449b2ca0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    清理 locator 相关 CHECK 约束中的历史冗余 NULL 分支。
    前置条件：
    - locator_kind / locator_value 已在 6f3449b2ca0b 中被设为 NOT NULL
    """

    # 1) ck_pol_locator_kind_allowed
    op.execute(
        """
        ALTER TABLE platform_order_lines
        DROP CONSTRAINT IF EXISTS ck_pol_locator_kind_allowed;
        """
    )
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ADD CONSTRAINT ck_pol_locator_kind_allowed
        CHECK (locator_kind IN ('FILLED_CODE', 'LINE_NO'));
        """
    )

    # 2) ck_pol_locator_kind_not_blank
    op.execute(
        """
        ALTER TABLE platform_order_lines
        DROP CONSTRAINT IF EXISTS ck_pol_locator_kind_not_blank;
        """
    )
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ADD CONSTRAINT ck_pol_locator_kind_not_blank
        CHECK (btrim(locator_kind) <> '');
        """
    )

    # 3) ck_pol_locator_value_not_blank
    op.execute(
        """
        ALTER TABLE platform_order_lines
        DROP CONSTRAINT IF EXISTS ck_pol_locator_value_not_blank;
        """
    )
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ADD CONSTRAINT ck_pol_locator_value_not_blank
        CHECK (btrim(locator_value) <> '');
        """
    )


def downgrade() -> None:
    """
    回滚为包含 NULL 分支的旧 CHECK 表达式（与 NOT NULL 并存，但语义冗余）。
    注意：不回滚 NOT NULL 本身。
    """

    # 1) ck_pol_locator_kind_allowed
    op.execute(
        """
        ALTER TABLE platform_order_lines
        DROP CONSTRAINT IF EXISTS ck_pol_locator_kind_allowed;
        """
    )
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ADD CONSTRAINT ck_pol_locator_kind_allowed
        CHECK (
            locator_kind IS NULL
            OR locator_kind IN ('FILLED_CODE', 'LINE_NO')
        );
        """
    )

    # 2) ck_pol_locator_kind_not_blank
    op.execute(
        """
        ALTER TABLE platform_order_lines
        DROP CONSTRAINT IF EXISTS ck_pol_locator_kind_not_blank;
        """
    )
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ADD CONSTRAINT ck_pol_locator_kind_not_blank
        CHECK (
            locator_kind IS NULL
            OR btrim(locator_kind) <> ''
        );
        """
    )

    # 3) ck_pol_locator_value_not_blank
    op.execute(
        """
        ALTER TABLE platform_order_lines
        DROP CONSTRAINT IF EXISTS ck_pol_locator_value_not_blank;
        """
    )
    op.execute(
        """
        ALTER TABLE platform_order_lines
        ADD CONSTRAINT ck_pol_locator_value_not_blank
        CHECK (
            locator_value IS NULL
            OR btrim(locator_value) <> ''
        );
        """
    )
