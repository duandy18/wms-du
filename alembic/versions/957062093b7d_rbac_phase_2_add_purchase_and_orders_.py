"""RBAC Phase 2 - add purchase.* and orders.read permissions, and bind roles.

新增权限：
- purchase.manage   : 采购单管理（创建 / 编辑 / 关闭 等）
- purchase.report   : 采购报表查看
- orders.read       : 订单数据阅读（列表 / 统计 / 明细，只读）

并根据最终五角色矩阵，重建角色权限集合：
- admin              : 所有权限
- operator           : 作业员（四大作业 + 运营报表 + 诊断）
- warehouse_manager  : 仓库主管 + 采购负责人（采购 + 盘点 + 主数据 + 报表 + 财务 + 诊断）
- finance            : 财务人员（财务 + 报表）
- ecommerce_operator : 电商运营（订单只读 + 报表 + 财务 + 主数据只读）

"""

from __future__ import annotations

from typing import Dict, Iterable, List

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "957062093b7d"
down_revision = "44660e5f2747"
branch_labels = None
depends_on = None


# ---------------------------
# 工具函数：确保权限 / 角色存在
# ---------------------------

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


def _load_permissions(conn) -> Dict[str, int]:
    rows = conn.execute(sa.text("SELECT id, name FROM permissions")).fetchall()
    return {name: int(pid) for pid, name in rows}


def _get_role_id(conn, name: str) -> int | None:
    row = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = :name"),
        {"name": name},
    ).first()
    return int(row[0]) if row else None


def _ensure_role(conn, name: str, description: str | None = None) -> int:
    rid = _get_role_id(conn, name)
    if rid is not None:
        return rid

    row = conn.execute(
        sa.text(
            """
            INSERT INTO roles (name, description)
            VALUES (:name, :description)
            RETURNING id
            """
        ),
        {"name": name, "description": description},
    ).first()
    return int(row[0])


def _set_role_permissions(
    conn,
    role_id: int,
    perm_names: Iterable[str],
    all_perms: Dict[str, int],
) -> None:
    """清空该角色现有权限，再绑定给定集合（幂等）。"""
    conn.execute(
        sa.text("DELETE FROM role_permissions WHERE role_id = :rid"),
        {"rid": role_id},
    )

    for name in perm_names:
        pid = all_perms.get(name)
        if pid is None:
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (:rid, :pid)
                ON CONFLICT DO NOTHING
                """
            ),
            {"rid": role_id, "pid": pid},
        )


def _grant_all_permissions(conn, role_id: int, all_perms: Dict[str, int]) -> None:
    """赋予角色所有权限（不清空，追加式）。"""
    for pid in all_perms.values():
        conn.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (:rid, :pid)
                ON CONFLICT DO NOTHING
                """
            ),
            {"rid": role_id, "pid": pid},
        )


# ---------------------------
# upgrade 主逻辑
# ---------------------------

def upgrade() -> None:
    conn = op.get_bind()

    # 1) 确保新增权限存在
    NEW_PERMS = [
        "purchase.manage",
        "purchase.report",
        "orders.read",
    ]
    for p in NEW_PERMS:
        _ensure_permission(conn, p)

    # 2) Reload 所有权限
    perms = _load_permissions(conn)

    # 3) 确保五个角色存在
    admin_id = _ensure_role(conn, "admin", "系统管理员（超级管理员）")
    operator_id = _ensure_role(conn, "operator", "作业员（仓库一线执行人员）")
    wh_id = _ensure_role(conn, "warehouse_manager", "仓库主管 / 采购负责人")
    finance_id = _ensure_role(conn, "finance", "财务人员")
    ecom_id = _ensure_role(conn, "ecommerce_operator", "电商运营人员")

    # 4) admin = 所有权限
    _grant_all_permissions(conn, admin_id, perms)

    # 5) operator（作业员）
    operator_perms: List[str] = [
        # 作业四项
        "operations.inbound",
        "operations.outbound",
        "operations.count",
        "operations.internal_outbound",
        # 报表（运营）
        "report.inventory",
        "report.outbound",
        # 诊断
        "diagnostics.trace",
        "diagnostics.ledger",
        "diagnostics.inventory",
    ]
    _set_role_permissions(conn, operator_id, operator_perms, perms)

    # 6) warehouse_manager（仓库主管 + 采购负责人）
    wh_perms: List[str] = [
        # 采购（新增能力）
        "purchase.manage",
        "purchase.report",
        # 盘点（管理）
        "operations.count",
        # 报表（含财务）
        "report.inventory",
        "report.outbound",
        "report.finance",
        # 诊断
        "diagnostics.trace",
        "diagnostics.ledger",
        "diagnostics.inventory",
        # 主数据写权限
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
        # 订单只读
        "orders.read",
    ]
    _set_role_permissions(conn, wh_id, wh_perms, perms)

    # 7) finance（财务人员）
    finance_perms: List[str] = [
        "report.inventory",
        "report.outbound",
        "report.finance",
        "purchase.report",
        "orders.read",
    ]
    _set_role_permissions(conn, finance_id, finance_perms, perms)

    # 8) ecommerce_operator（电商运营）
    ecom_perms: List[str] = [
        "orders.read",
        "report.inventory",
        "report.outbound",
        "report.finance",
        "purchase.report",
        # 主数据只读
        "config.store.read",
        "config.warehouse.read",
        "config.item.read",
        "config.supplier.read",
        "config.shipping_provider.read",
    ]
    _set_role_permissions(conn, ecom_id, ecom_perms, perms)


def downgrade() -> None:
    """不做回滚（RBAC 配置不建议自动降级）。"""
    pass
