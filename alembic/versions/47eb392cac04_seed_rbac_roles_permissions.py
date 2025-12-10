from __future__ import annotations

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision: str = "47eb392cac04"
down_revision: Union[str, Sequence[str], None] = "4cbadbf3083e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    RBAC 初始化（仅数据）
    - 创建角色：admin / operator
    - 创建关键权限
    - admin → 所有权限
    - operator → 非 system.* / 非 dev.* 权限
    - 若存在 username='admin' 且 primary_role_id NULL → 挂到 admin 角色
    """
    bind = op.get_bind()

    # ---------------------------
    # 1) 创建角色：admin / operator
    # ---------------------------
    roles = {
        "admin": "系统管理员（超级管理员）",
        "operator": "操作员（除系统管理/开发者工具外拥有业务权限）",
    }

    for name, desc in roles.items():
        bind.execute(
            text("""
                INSERT INTO roles (name, description)
                VALUES (:name, :desc)
                ON CONFLICT (name) DO NOTHING
            """),
            {"name": name, "desc": desc},
        )

    # 获取角色 id
    rows = bind.execute(
        text("SELECT id, name FROM roles WHERE name IN ('admin','operator')")
    ).mappings()

    role_ids = {row["name"]: row["id"] for row in rows}

    admin_role_id = role_ids.get("admin")
    operator_role_id = role_ids.get("operator")

    if not admin_role_id or not operator_role_id:
        # 表结构可能异常，直接返回
        return

    # ---------------------------
    # 2) 创建核心权限（根据你系统现状）
    # ---------------------------
    permission_names = [
        # System Admin（系统管理）
        "system.user.manage",
        "system.role.manage",
        "system.permission.manage",
        # Dev Tools
        "dev.tools.access",
        # Config（基础配置）
        "config.store.read",
        "config.store.write",
        "config.warehouse.read",
        "config.warehouse.write",
        "config.item.read",
        "config.item.write",
        "config.supplier.read",
        "config.supplier.write",
        "config.shipping_provider.read",
        "config.shipping_provider.write",
        # Operations（作业区）
        "operations.inbound",
        "operations.outbound",
        "operations.count",
        "operations.internal_outbound",
    ]

    for pname in permission_names:
        bind.execute(
            text("""
                INSERT INTO permissions (name)
                VALUES (:name)
                ON CONFLICT (name) DO NOTHING
            """),
            {"name": pname},
        )

    # ---------------------------
    # 3) admin ← 所有权限
    # ---------------------------
    bind.execute(
        text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT :rid, p.id
            FROM permissions AS p
            ON CONFLICT (role_id, permission_id) DO NOTHING
        """),
        {"rid": admin_role_id},
    )

    # ---------------------------
    # 4) operator ← 非 system.* / 非 dev.* 权限
    # ---------------------------
    bind.execute(
        text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT :rid, p.id
              FROM permissions AS p
             WHERE p.name NOT LIKE 'system.%'
               AND p.name NOT LIKE 'dev.%'
            ON CONFLICT DO NOTHING
        """),
        {"rid": operator_role_id},
    )

    # ---------------------------
    # 5) 若存在 admin 用户且 primary_role_id 为空 → 掛 admin 角色
    # ---------------------------
    bind.execute(
        text("""
            UPDATE users
               SET primary_role_id = :admin_role_id
             WHERE username = 'admin'
               AND (primary_role_id IS NULL OR primary_role_id = 0)
        """),
        {"admin_role_id": admin_role_id},
    )

    # 同时写入 user_roles（多角色表）
    bind.execute(
        text("""
            INSERT INTO user_roles (user_id, role_id)
            SELECT u.id, :admin_role_id
              FROM users AS u
             WHERE u.username = 'admin'
            ON CONFLICT (user_id, role_id) DO NOTHING
        """),
        {"admin_role_id": admin_role_id},
    )


def downgrade() -> None:
    """
    数据初始化不安全删除，保持空实现。
    """
    pass
