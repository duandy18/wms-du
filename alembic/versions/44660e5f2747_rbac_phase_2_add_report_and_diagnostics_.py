"""RBAC Phase 2 - add report / diagnostics permissions.

- 新增一组菜单级权限，用于库存报表 / 财务分析 / 诊断工具：
  - report.inventory
  - report.outbound
  - report.finance
  - diagnostics.trace
  - diagnostics.ledger
  - diagnostics.inventory

- 将这些权限授予 admin
- 将其中一部分授予 operator（你可以后续调整）
"""

from __future__ import annotations
from typing import Dict

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "44660e5f2747"
down_revision = "47eb392cac04"
branch_labels = None
depends_on = None


# ----------------------
# 辅助函数：确保权限存在
# ----------------------
def _ensure_permission(conn, name: str) -> int:
    row = conn.execute(
        sa.text("SELECT id FROM permissions WHERE name = :name"),
        {"name": name},
    ).first()

    if row:
        return int(row[0])

    row = conn.execute(
        sa.text(
            """
            INSERT INTO permissions (name)
            VALUES (:name)
            RETURNING id
            """
        ),
        {"name": name},
    ).first()

    return int(row[0])


def _get_role_id(conn, name: str) -> int | None:
    row = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = :name"),
        {"name": name},
    ).first()
    return int(row[0]) if row else None


def _ensure_role_permission(conn, role_id: int, permission_id: int) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES (:role_id, :permission_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"role_id": role_id, "permission_id": permission_id},
    )


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 新增的权限名
    new_permission_names = [
        "report.inventory",       # Snapshot / 渠道库存
        "report.outbound",        # 出库 Dashboard / 发货报表 / 发货账本
        "report.finance",         # Finance* 财务分析页面
        "diagnostics.trace",      # Trace Studio
        "diagnostics.ledger",     # Ledger Studio
        "diagnostics.inventory",  # Inventory Studio
    ]

    # 2) 创建 / 获取所有权限
    perm_ids: Dict[str, int] = {}
    for name in new_permission_names:
        perm_ids[name] = _ensure_permission(conn, name)

    # 3) admin / operator 角色 ID
    admin_role_id = _get_role_id(conn, "admin")
    operator_role_id = _get_role_id(conn, "operator")

    # 4) admin：拿到全部新权限
    if admin_role_id is not None:
        for pid in perm_ids.values():
            _ensure_role_permission(conn, admin_role_id, pid)

    # 5) operator：拥有所有报表 & 诊断读权限（如需调整，未来在角色管理页面即可）
    if operator_role_id is not None:
        operator_perm_names = [
            "report.inventory",
            "report.outbound",
            "report.finance",
            "diagnostics.trace",
            "diagnostics.ledger",
            "diagnostics.inventory",
        ]
        for name in operator_perm_names:
            pid = perm_ids.get(name)
            if pid is not None:
                _ensure_role_permission(conn, operator_role_id, pid)


def downgrade() -> None:
    """
    降级不删除角色和权限（RBAC 数据通常不可逆）。占位即可。
    """
    pass
