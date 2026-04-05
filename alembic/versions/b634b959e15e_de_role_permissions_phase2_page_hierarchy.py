# alembic/versions/b634b959e15e_de_role_permissions_phase2_page_hierarchy.py
"""de_role_permissions_phase2_page_hierarchy

Revision ID: b634b959e15e
Revises: 6dbcda2dc5fc
Create Date: 2026-04-05 15:28:08.287517

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b634b959e15e"
down_revision: Union[str, Sequence[str], None] = "6dbcda2dc5fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 先解除 phase1 的“页面=独占权限”约束，允许后续父子页共享同一组权限
    op.drop_constraint(
        "uq_page_registry_read_permission_id",
        "page_registry",
        type_="unique",
    )
    op.drop_constraint(
        "uq_page_registry_write_permission_id",
        "page_registry",
        type_="unique",
    )

    # 2) 新增层级页面所需字段；先允许为空，完成回填后再收紧
    op.add_column(
        "page_registry",
        sa.Column("parent_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "page_registry",
        sa.Column("level", sa.Integer(), nullable=True),
    )
    op.add_column(
        "page_registry",
        sa.Column("domain_code", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "page_registry",
        sa.Column("show_in_topbar", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "page_registry",
        sa.Column("show_in_sidebar", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "page_registry",
        sa.Column("inherit_permissions", sa.Boolean(), nullable=True),
    )

    # 3) 允许 read/write 权限为空，为二级页面“继承父级权限”做准备
    op.alter_column(
        "page_registry",
        "read_permission_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "page_registry",
        "write_permission_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 4) 回填当前 8 个一级页面
    # 当前阶段一级页面仍是权限主边界，因此：
    # - level = 1
    # - parent_code = NULL
    # - domain_code 先统一记为 wms（真实领域先在二级页面上表达）
    # - topbar=true / sidebar=false
    # - inherit_permissions=false，继续持有自身 read/write 权限
    op.execute(
        """
        UPDATE page_registry
           SET parent_code = NULL,
               level = 1,
               domain_code = 'wms',
               show_in_topbar = TRUE,
               show_in_sidebar = FALSE,
               inherit_permissions = FALSE
        """
    )

    # 5) 将新增字段收紧为非空（parent_code 例外）
    op.alter_column(
        "page_registry",
        "level",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "page_registry",
        "domain_code",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.alter_column(
        "page_registry",
        "show_in_topbar",
        existing_type=sa.Boolean(),
        nullable=False,
    )
    op.alter_column(
        "page_registry",
        "show_in_sidebar",
        existing_type=sa.Boolean(),
        nullable=False,
    )
    op.alter_column(
        "page_registry",
        "inherit_permissions",
        existing_type=sa.Boolean(),
        nullable=False,
    )

    # 6) 增加父子页关联与索引
    op.create_foreign_key(
        "fk_page_registry_parent_code_page_registry",
        "page_registry",
        "page_registry",
        ["parent_code"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_page_registry_parent_code",
        "page_registry",
        ["parent_code"],
        unique=False,
    )

    # 7) 加约束，正式把 page_registry 升级为“层级页面表”
    op.create_check_constraint(
        "ck_page_registry_level",
        "page_registry",
        "level IN (1, 2)",
    )
    op.create_check_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        "domain_code IN ('oms', 'pms', 'procurement', 'wms', 'tms')",
    )
    op.create_check_constraint(
        "ck_page_registry_parent_level_consistency",
        "page_registry",
        "("
        "  (level = 1 AND parent_code IS NULL)"
        "  OR "
        "  (level = 2 AND parent_code IS NOT NULL)"
        ")",
    )
    op.create_check_constraint(
        "ck_page_registry_permission_inherit_consistency",
        "page_registry",
        "("
        "  ("
        "    inherit_permissions = TRUE"
        "    AND read_permission_id IS NULL"
        "    AND write_permission_id IS NULL"
        "  )"
        "  OR "
        "  ("
        "    inherit_permissions = FALSE"
        "    AND read_permission_id IS NOT NULL"
        "    AND write_permission_id IS NOT NULL"
        "  )"
        ")",
    )


def downgrade() -> None:
    # phase2a 的回滚假定 phase2b 已先回滚，因此不存在二级页面残留
    op.drop_constraint(
        "ck_page_registry_permission_inherit_consistency",
        "page_registry",
        type_="check",
    )
    op.drop_constraint(
        "ck_page_registry_parent_level_consistency",
        "page_registry",
        type_="check",
    )
    op.drop_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        type_="check",
    )
    op.drop_constraint(
        "ck_page_registry_level",
        "page_registry",
        type_="check",
    )

    op.drop_index("ix_page_registry_parent_code", table_name="page_registry")
    op.drop_constraint(
        "fk_page_registry_parent_code_page_registry",
        "page_registry",
        type_="foreignkey",
    )

    # 恢复 phase1 约束前，先把 read/write 权限列收回非空
    op.alter_column(
        "page_registry",
        "read_permission_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "page_registry",
        "write_permission_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.create_unique_constraint(
        "uq_page_registry_read_permission_id",
        "page_registry",
        ["read_permission_id"],
    )
    op.create_unique_constraint(
        "uq_page_registry_write_permission_id",
        "page_registry",
        ["write_permission_id"],
    )

    op.drop_column("page_registry", "inherit_permissions")
    op.drop_column("page_registry", "show_in_sidebar")
    op.drop_column("page_registry", "show_in_topbar")
    op.drop_column("page_registry", "domain_code")
    op.drop_column("page_registry", "level")
    op.drop_column("page_registry", "parent_code")
