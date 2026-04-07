"""clear_legacy_rbac_historical_data

Revision ID: 0154b7a40db0
Revises: 934e13334b3f
Create Date: 2026-04-06 22:15:14.018763

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0154b7a40db0"
down_revision: Union[str, Sequence[str], None] = "934e13334b3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_PRIMARY_ROLE_BAK = "rbac_hist_bak_user_primary_role_0154b7a40db0"
USER_ROLES_BAK = "rbac_hist_bak_user_roles_0154b7a40db0"
ROLE_PERMS_BAK = "rbac_hist_bak_role_permissions_0154b7a40db0"


def upgrade() -> None:
    """
    清空旧 RBAC 历史数据，但先做备份以支持 downgrade：

    1) 备份 users.primary_role_id 非空记录
    2) 备份 user_roles
    3) 备份 role_permissions
    4) 将 users.primary_role_id 置空
    5) 清空 user_roles
    6) 清空 role_permissions

    注意：
    - 不删除 roles 表
    - 不删除 users.primary_role_id 字段
    - 不删除 user_roles / role_permissions 表结构
    - 仅清空历史数据
    """
    op.create_table(
        USER_PRIMARY_ROLE_BAK,
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("primary_role_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        USER_ROLES_BAK,
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    op.create_table(
        ROLE_PERMS_BAK,
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    conn = op.get_bind()

    conn.execute(
        sa.text(
            f"""
            INSERT INTO {USER_PRIMARY_ROLE_BAK} (user_id, primary_role_id)
            SELECT id, primary_role_id
            FROM users
            WHERE primary_role_id IS NOT NULL
            """
        )
    )

    conn.execute(
        sa.text(
            f"""
            INSERT INTO {USER_ROLES_BAK} (user_id, role_id)
            SELECT user_id, role_id
            FROM user_roles
            """
        )
    )

    conn.execute(
        sa.text(
            f"""
            INSERT INTO {ROLE_PERMS_BAK} (role_id, permission_id)
            SELECT role_id, permission_id
            FROM role_permissions
            """
        )
    )

    conn.execute(
        sa.text(
            """
            UPDATE users
               SET primary_role_id = NULL
             WHERE primary_role_id IS NOT NULL
            """
        )
    )

    conn.execute(sa.text("DELETE FROM user_roles"))
    conn.execute(sa.text("DELETE FROM role_permissions"))


def downgrade() -> None:
    """
    从 upgrade 创建的备份表恢复旧 RBAC 历史数据：

    1) 恢复 users.primary_role_id
    2) 恢复 user_roles
    3) 恢复 role_permissions
    4) 删除备份表
    """
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            UPDATE users
               SET primary_role_id = NULL
             WHERE primary_role_id IS NOT NULL
            """
        )
    )

    conn.execute(
        sa.text(
            f"""
            UPDATE users u
               SET primary_role_id = b.primary_role_id
              FROM {USER_PRIMARY_ROLE_BAK} b
             WHERE u.id = b.user_id
            """
        )
    )

    conn.execute(sa.text("DELETE FROM user_roles"))
    conn.execute(
        sa.text(
            f"""
            INSERT INTO user_roles (user_id, role_id)
            SELECT user_id, role_id
            FROM {USER_ROLES_BAK}
            """
        )
    )

    conn.execute(sa.text("DELETE FROM role_permissions"))
    conn.execute(
        sa.text(
            f"""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT role_id, permission_id
            FROM {ROLE_PERMS_BAK}
            """
        )
    )

    op.drop_table(ROLE_PERMS_BAK)
    op.drop_table(USER_ROLES_BAK)
    op.drop_table(USER_PRIMARY_ROLE_BAK)
