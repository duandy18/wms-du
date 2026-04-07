"""drop_legacy_rbac_schema

Revision ID: 528dd15892b9
Revises: 0154b7a40db0
Create Date: 2026-04-07 01:50:21.888150

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "528dd15892b9"
down_revision: Union[str, Sequence[str], None] = "0154b7a40db0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    彻底退休 legacy RBAC schema：

    - 删除 users.primary_role_id
    - 删除 user_roles
    - 删除 role_permissions
    - 删除 roles

    前置假设：
    - 旧 RBAC 历史数据已在上一份 migration 中清空
    - 应用代码已脱离 Role / user_roles / role_permissions / primary_role_id
    """
    op.drop_column("users", "primary_role_id")
    op.drop_table("role_permissions")
    op.drop_table("user_roles")
    op.drop_table("roles")


def downgrade() -> None:
    """
    最小可逆回滚：

    - 重建 roles
    - 重建 user_roles
    - 重建 role_permissions
    - 重建 users.primary_role_id

    注意：
    - 仅恢复结构，不恢复历史数据
    """
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="roles_pkey"),
        sa.UniqueConstraint("name", name="roles_name_key"),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_user_roles_role_id_roles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_roles_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name="pk_user_roles"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id_role_id"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_role_permissions_role_id_roles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
    )

    op.add_column("users", sa.Column("primary_role_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_primary_role_id_roles",
        "users",
        "roles",
        ["primary_role_id"],
        ["id"],
        ondelete="SET NULL",
    )
