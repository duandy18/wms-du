"""wms_phase3_expand_page_registry_to_three_levels

Revision ID: 711e3a1495a6
Revises: dcd0f7b59422
Create Date: 2026-04-07 16:44:52.588278

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "711e3a1495a6"
down_revision: Union[str, Sequence[str], None] = "dcd0f7b59422"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand page_registry from 2 levels to 3 levels.

    Phase3-1 只做“能力扩容”，不做任何页面 seed / route_prefix 重挂 / 旧树退役。
    当前阶段先把 DB 约束放宽到允许 1/2/3 三层：
    - level=1: parent_code must be NULL
    - level=2 or 3: parent_code must be NOT NULL

    更严格的“二级父必须是一级 / 三级父必须是二级”约束，
    放到后续数据迁移与导航服务切换阶段收口，不在本 migration 里硬写跨行校验。
    """
    op.drop_constraint(
        "ck_page_registry_parent_level_consistency",
        "page_registry",
        type_="check",
    )
    op.drop_constraint(
        "ck_page_registry_level",
        "page_registry",
        type_="check",
    )

    op.create_check_constraint(
        "ck_page_registry_level",
        "page_registry",
        "level IN (1, 2, 3)",
    )
    op.create_check_constraint(
        "ck_page_registry_parent_level_consistency",
        "page_registry",
        "((level = 1 AND parent_code IS NULL) "
        "OR (level IN (2, 3) AND parent_code IS NOT NULL))",
    )


def downgrade() -> None:
    """Restore page_registry back to 2 levels.

    注意：
    - 本回滚假定后续 phase3 seed / rebind / retire migrations 已先回滚
    - 如果 page_registry 中仍存在 level=3 记录，则拒绝回滚，避免静默破坏数据
    """
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM page_registry
            WHERE level = 3
          ) THEN
            RAISE EXCEPTION
              'Cannot downgrade 711e3a1495a6 while level=3 pages still exist. Roll back later phase3 page migrations first.';
          END IF;
        END
        $$;
        """
    )

    op.drop_constraint(
        "ck_page_registry_parent_level_consistency",
        "page_registry",
        type_="check",
    )
    op.drop_constraint(
        "ck_page_registry_level",
        "page_registry",
        type_="check",
    )

    op.create_check_constraint(
        "ck_page_registry_level",
        "page_registry",
        "level IN (1, 2)",
    )
    op.create_check_constraint(
        "ck_page_registry_parent_level_consistency",
        "page_registry",
        "((level = 1 AND parent_code IS NULL) "
        "OR (level = 2 AND parent_code IS NOT NULL))",
    )
