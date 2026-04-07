"""retire_legacy_admin_user_permissions

Revision ID: 791d5b739298
Revises: 333721a88b19
Create Date: 2026-04-06 21:18:02.848043

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "791d5b739298"
down_revision: Union[str, Sequence[str], None] = "333721a88b19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 只清 runtime 真相源 user_permissions 中的旧 admin 权限残留
    # 不删除 permissions 表定义
    # 不动 system.role.manage
    # 不动 role_permissions
    op.execute(
        """
        DELETE FROM user_permissions up
        USING permissions p
        WHERE up.permission_id = p.id
          AND p.name IN ('system.user.manage', 'system.permission.manage')
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 最小可回滚：
    # 把旧 admin 权限补回到当前拥有 page.admin.read/write 的用户。
    # 不追求逐条历史精确恢复，只保证 admin 主线权限集合可逆近似恢复。
    op.execute(
        """
        WITH target_users AS (
          SELECT DISTINCT up.user_id
          FROM user_permissions up
          JOIN permissions p
            ON p.id = up.permission_id
          WHERE p.name IN ('page.admin.read', 'page.admin.write')
        ),
        legacy_permissions AS (
          SELECT id
          FROM permissions
          WHERE name IN ('system.user.manage', 'system.permission.manage')
        )
        INSERT INTO user_permissions (user_id, permission_id)
        SELECT tu.user_id, lp.id
        FROM target_users tu
        CROSS JOIN legacy_permissions lp
        ON CONFLICT DO NOTHING
        """
    )
