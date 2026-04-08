"""retire_legacy_admin_permission_definitions

Revision ID: d62cc07bb5c9
Revises: b8899b8d73a2
Create Date: 2026-04-08 18:42:15.977906

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d62cc07bb5c9"
down_revision: Union[str, Sequence[str], None] = "b8899b8d73a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_ADMIN_PERMISSION_NAMES = (
    "system.user.manage",
    "system.role.manage",
    "system.permission.manage",
)


def upgrade() -> None:
    """
    第二阶段：admin 旧 system.* 权限字典正式退役。

    当前前提：
    - runtime 真相源已经切到 page.admin.read / page.admin.write
    - user_permissions 中的旧 system.* 残留已在更早迁移中清掉
    - 本迁移只负责删除 permissions 表中的旧定义

    守卫策略：
    - 若 page_registry 仍引用这些旧权限，则直接失败，不做猜测性删除
    """
    conn = op.get_bind()

    # 1) 防御式清理：即使理论上已为 0，也再清一次 user_permissions 中的旧残留
    conn.execute(
        sa.text(
            """
            DELETE FROM user_permissions up
            USING permissions p
            WHERE up.permission_id = p.id
              AND p.name IN (
                'system.user.manage',
                'system.role.manage',
                'system.permission.manage'
              )
            """
        )
    )

    # 2) 守卫：如果 page_registry 仍引用这些旧权限，直接失败
    refs = conn.execute(
        sa.text(
            """
            WITH legacy_permissions AS (
              SELECT id, name
              FROM permissions
              WHERE name IN (
                'system.user.manage',
                'system.role.manage',
                'system.permission.manage'
              )
            ),
            page_refs AS (
              SELECT pr.code, lp.name
              FROM page_registry pr
              JOIN legacy_permissions lp
                ON lp.id = pr.read_permission_id

              UNION ALL

              SELECT pr.code, lp.name
              FROM page_registry pr
              JOIN legacy_permissions lp
                ON lp.id = pr.write_permission_id
            )
            SELECT code, name
            FROM page_refs
            ORDER BY code, name
            """
        )
    ).fetchall()

    if refs:
        detail = ", ".join(f"{code} -> {name}" for code, name in refs)
        raise RuntimeError(
            "legacy admin permissions are still referenced by page_registry: " + detail
        )

    # 3) 删除旧 permissions 字典项
    conn.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE name IN (
              'system.user.manage',
              'system.role.manage',
              'system.permission.manage'
            )
            """
        )
    )


def downgrade() -> None:
    """
    最小可逆回滚：
    - 只恢复 permissions 表字典项
    - 不自动回填 user_permissions

    原因：
    本迁移升级前的真实状态就是 definitions 仍存在，
    但 runtime 用户已不再持有这些旧权限。
    """
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            INSERT INTO permissions (name)
            VALUES
              ('system.user.manage'),
              ('system.role.manage'),
              ('system.permission.manage')
            ON CONFLICT (name) DO NOTHING
            """
        )
    )
