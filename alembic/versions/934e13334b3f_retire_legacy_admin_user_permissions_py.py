"""retire_legacy_role_manage_user_permissions

Revision ID: 934e13334b3f
Revises: 791d5b739298
Create Date: 2026-04-06 21:58:22.126346

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "934e13334b3f"
down_revision: Union[str, Sequence[str], None] = "791d5b739298"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    退休 system.role.manage 的 runtime 残留：

    - 只删除 user_permissions 中的 system.role.manage
    - 不删除 permissions 表中字典项
    - 不动 roles / user_roles / role_permissions
    - 不动 users.primary_role_id
    """
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            DELETE FROM user_permissions up
            USING permissions p
            WHERE up.permission_id = p.id
              AND p.name = 'system.role.manage'
            """
        )
    )


def downgrade() -> None:
    """
    最小可逆回滚：

    - 将 system.role.manage 回补给当前拥有 page.admin.read 或 page.admin.write 的用户
    - 不改 roles / user_roles / role_permissions 历史数据
    """
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            INSERT INTO user_permissions (user_id, permission_id)
            SELECT DISTINCT
                up.user_id,
                p_role.id
            FROM user_permissions up
            JOIN permissions p_admin
              ON p_admin.id = up.permission_id
            JOIN permissions p_role
              ON p_role.name = 'system.role.manage'
            WHERE p_admin.name IN ('page.admin.read', 'page.admin.write')
            ON CONFLICT (user_id, permission_id) DO NOTHING
            """
        )
    )
