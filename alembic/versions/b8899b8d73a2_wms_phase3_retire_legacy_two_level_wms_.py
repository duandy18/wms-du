"""wms_phase3_retire_legacy_two_level_wms_tree

Revision ID: b8899b8d73a2
Revises: e30e6d37f7f9
Create Date: 2026-04-07 18:23:20.634000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b8899b8d73a2"
down_revision: Union[str, Sequence[str], None] = "e30e6d37f7f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_WMS_ROOT_CODES = (
    "wms.order_outbound",
    "wms.order_management",
    "wms.logistics",
    "wms.analytics",
    "wms.masterdata",
    "wms.internal_ops",
)

LEGACY_WMS_SHELL_CODES = (
    "wms.inbound.receiving",
    "wms.internal_ops.count",
    "wms.internal_ops.internal_outbound",
    "wms.order_outbound.pick_tasks",
    "wms.order_outbound.dashboard",
    "wms.masterdata.warehouses",
)

LEGACY_WMS_PERMISSION_NAMES = (
    "page.wms.inbound.read",
    "page.wms.inbound.write",
    "page.wms.order_outbound.read",
    "page.wms.order_outbound.write",
    "page.wms.order_management.read",
    "page.wms.order_management.write",
    "page.wms.logistics.read",
    "page.wms.logistics.write",
    "page.wms.internal_ops.read",
    "page.wms.internal_ops.write",
    "page.wms.inventory.read",
    "page.wms.inventory.write",
    "page.wms.analytics.read",
    "page.wms.analytics.write",
    "page.wms.masterdata.read",
    "page.wms.masterdata.write",
)


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 先删旧细二级壳
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'wms.inbound.receiving',
          'wms.internal_ops.count',
          'wms.internal_ops.internal_outbound',
          'wms.order_outbound.pick_tasks',
          'wms.order_outbound.dashboard',
          'wms.masterdata.warehouses'
        )
        """
    )

    # 2) 再删旧一级壳
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'wms.order_outbound',
          'wms.order_management',
          'wms.logistics',
          'wms.analytics',
          'wms.masterdata',
          'wms.internal_ops'
        )
        """
    )

    # 3) 最后删旧 page.wms.* 权限字典项
    # user_permissions 上是 ON DELETE CASCADE，会自动清掉用户上的旧权限残留
    op.execute(
        """
        DELETE FROM permissions
        WHERE name IN (
          'page.wms.inbound.read',
          'page.wms.inbound.write',
          'page.wms.order_outbound.read',
          'page.wms.order_outbound.write',
          'page.wms.order_management.read',
          'page.wms.order_management.write',
          'page.wms.logistics.read',
          'page.wms.logistics.write',
          'page.wms.internal_ops.read',
          'page.wms.internal_ops.write',
          'page.wms.inventory.read',
          'page.wms.inventory.write',
          'page.wms.analytics.read',
          'page.wms.analytics.write',
          'page.wms.masterdata.read',
          'page.wms.masterdata.write'
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 恢复旧 page.wms.* 权限定义
    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES
          ('page.wms.inbound.read'),
          ('page.wms.inbound.write'),
          ('page.wms.order_outbound.read'),
          ('page.wms.order_outbound.write'),
          ('page.wms.order_management.read'),
          ('page.wms.order_management.write'),
          ('page.wms.logistics.read'),
          ('page.wms.logistics.write'),
          ('page.wms.internal_ops.read'),
          ('page.wms.internal_ops.write'),
          ('page.wms.inventory.read'),
          ('page.wms.inventory.write'),
          ('page.wms.analytics.read'),
          ('page.wms.analytics.write'),
          ('page.wms.masterdata.read'),
          ('page.wms.masterdata.write')
        ON CONFLICT (name) DO NOTHING
        """
    )

    # 2) 恢复旧一级壳
    op.execute(
        """
        INSERT INTO page_registry (
          code,
          name,
          parent_code,
          level,
          domain_code,
          show_in_topbar,
          show_in_sidebar,
          inherit_permissions,
          read_permission_id,
          write_permission_id,
          sort_order,
          is_active
        )
        VALUES
          (
            'wms.order_outbound',
            '订单出库',
            NULL,
            1,
            'wms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.wms.order_outbound.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.order_outbound.write'),
            20,
            TRUE
          ),
          (
            'wms.order_management',
            '订单管理',
            NULL,
            1,
            'wms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.wms.order_management.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.order_management.write'),
            30,
            TRUE
          ),
          (
            'wms.logistics',
            '物流',
            NULL,
            1,
            'wms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.wms.logistics.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.logistics.write'),
            40,
            TRUE
          ),
          (
            'wms.internal_ops',
            '仓内作业',
            NULL,
            1,
            'wms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.wms.internal_ops.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.internal_ops.write'),
            50,
            TRUE
          ),
          (
            'wms.analytics',
            '财务分析',
            NULL,
            1,
            'wms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.wms.analytics.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.analytics.write'),
            70,
            TRUE
          ),
          (
            'wms.masterdata',
            '主数据',
            NULL,
            1,
            'wms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.wms.masterdata.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.masterdata.write'),
            80,
            TRUE
          )
        ON CONFLICT (code) DO UPDATE
        SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 3) 恢复旧细二级壳
    op.execute(
        """
        INSERT INTO page_registry (
          code,
          name,
          parent_code,
          level,
          domain_code,
          show_in_topbar,
          show_in_sidebar,
          inherit_permissions,
          read_permission_id,
          write_permission_id,
          sort_order,
          is_active
        )
        VALUES
          (
            'wms.inbound.receiving',
            '原子入库',
            'wms.inbound',
            2,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'wms.internal_ops.count',
            '盘点作业',
            'wms.internal_ops',
            2,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'wms.internal_ops.internal_outbound',
            '内部出库',
            'wms.internal_ops',
            2,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          ),
          (
            'wms.order_outbound.pick_tasks',
            '拣货任务',
            'wms.order_outbound',
            2,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'wms.order_outbound.dashboard',
            '出库看板',
            'wms.order_outbound',
            2,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          ),
          (
            'wms.masterdata.warehouses',
            '仓库管理',
            'wms.masterdata',
            2,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          )
        ON CONFLICT (code) DO UPDATE
        SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 4) 最小可逆近似恢复：
    #    把当前新一级页权限，近似补回到旧 page.wms.* 权限。
    #    不追求逐条历史精确恢复，只保证退役迁移可逆。
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.wms.read' AS source_name, 'page.wms.inbound.read' AS target_name
          UNION ALL
          SELECT 'page.wms.write', 'page.wms.inbound.write'
          UNION ALL
          SELECT 'page.wms.read', 'page.wms.order_outbound.read'
          UNION ALL
          SELECT 'page.wms.write', 'page.wms.order_outbound.write'
          UNION ALL
          SELECT 'page.wms.read', 'page.wms.internal_ops.read'
          UNION ALL
          SELECT 'page.wms.write', 'page.wms.internal_ops.write'
          UNION ALL
          SELECT 'page.wms.read', 'page.wms.inventory.read'
          UNION ALL
          SELECT 'page.wms.write', 'page.wms.inventory.write'
          UNION ALL
          SELECT 'page.oms.read', 'page.wms.order_management.read'
          UNION ALL
          SELECT 'page.oms.write', 'page.wms.order_management.write'
          UNION ALL
          SELECT 'page.tms.read', 'page.wms.logistics.read'
          UNION ALL
          SELECT 'page.tms.write', 'page.wms.logistics.write'
          UNION ALL
          SELECT 'page.analytics.read', 'page.wms.analytics.read'
          UNION ALL
          SELECT 'page.analytics.write', 'page.wms.analytics.write'
          UNION ALL
          SELECT 'page.pms.read', 'page.wms.masterdata.read'
          UNION ALL
          SELECT 'page.pms.write', 'page.wms.masterdata.write'
        ),
        pairs AS (
          SELECT DISTINCT
            up.user_id AS user_id,
            tp.id AS permission_id
          FROM mappings m
          JOIN permissions sp
            ON sp.name = m.source_name
          JOIN user_permissions up
            ON up.permission_id = sp.id
          JOIN permissions tp
            ON tp.name = m.target_name
        )
        INSERT INTO user_permissions (user_id, permission_id)
        SELECT user_id, permission_id
        FROM pairs
        ON CONFLICT (user_id, permission_id) DO NOTHING
        """
    )
