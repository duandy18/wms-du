"""wms_phase3_seed_three_level_wms_pages

Revision ID: 01ba4e53a8a6
Revises: f69be92871c7
Create Date: 2026-04-07 17:07:49.726738

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "01ba4e53a8a6"
down_revision: Union[str, Sequence[str], None] = "f69be92871c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 建 / 改 WMS 二级页
    # 说明：
    # - wms.inbound / wms.inventory 复用旧 code，从旧一级改挂为 wms 下二级
    # - wms.outbound / wms.count / wms.warehouses 为新增二级
    # - 二级统一继承一级 wms 权限，不单独持有 page 权限
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
            'wms.inventory',
            '库存',
            'wms',
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
            'wms.inbound',
            '入库',
            'wms',
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
            'wms.outbound',
            '出库',
            'wms',
            2,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            30,
            TRUE
          ),
          (
            'wms.count',
            '盘点',
            'wms',
            2,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            40,
            TRUE
          ),
          (
            'wms.warehouses',
            '仓库管理',
            'wms',
            2,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            50,
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

    # 2) 建 / 改 WMS 三级页
    # 说明：
    # - wms.inventory.snapshot / wms.inventory.ledger 复用旧 code，
    #   从旧二级改挂为 wms.inventory 下三级
    # - count.adjustments 当前先建节点，但默认不激活
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
            'wms.inventory.snapshot',
            '库存快照',
            'wms.inventory',
            3,
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
            'wms.inventory.ledger',
            '库存台账',
            'wms.inventory',
            3,
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
            'wms.inbound.atomic',
            '原子入库',
            'wms.inbound',
            3,
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
            'wms.inbound.purchase',
            '采购入库',
            'wms.inbound',
            3,
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
            'wms.inbound.returns',
            '退货入库',
            'wms.inbound',
            3,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            30,
            TRUE
          ),
          (
            'wms.outbound.atomic',
            '原子出库',
            'wms.outbound',
            3,
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
            'wms.outbound.order',
            '订单出库',
            'wms.outbound',
            3,
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
            'wms.count.tasks',
            '盘点作业',
            'wms.count',
            3,
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
            'wms.count.adjustments',
            '库存调整',
            'wms.count',
            3,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            FALSE
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


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 先删除本次新增的三级页
    # 注意：
    # - wms.inventory.snapshot / wms.inventory.ledger 是复用旧 code，不能删，只能还原
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'wms.inbound.atomic',
          'wms.inbound.purchase',
          'wms.inbound.returns',
          'wms.outbound.atomic',
          'wms.outbound.order',
          'wms.count.tasks',
          'wms.count.adjustments'
        )
        """
    )

    # 2) 还原复用的 inventory 两个旧页：挂回旧 wms.inventory 一级页下的二级页
    op.execute(
        """
        UPDATE page_registry
        SET
          name = '库存快照',
          parent_code = 'wms.inventory',
          level = 2,
          domain_code = 'wms',
          show_in_topbar = FALSE,
          show_in_sidebar = TRUE,
          inherit_permissions = TRUE,
          read_permission_id = NULL,
          write_permission_id = NULL,
          sort_order = 10,
          is_active = TRUE
        WHERE code = 'wms.inventory.snapshot'
        """
    )

    op.execute(
        """
        UPDATE page_registry
        SET
          name = '库存台账',
          parent_code = 'wms.inventory',
          level = 2,
          domain_code = 'wms',
          show_in_topbar = FALSE,
          show_in_sidebar = TRUE,
          inherit_permissions = TRUE,
          read_permission_id = NULL,
          write_permission_id = NULL,
          sort_order = 20,
          is_active = TRUE
        WHERE code = 'wms.inventory.ledger'
        """
    )

    # 3) 删除本次新增的二级页
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'wms.outbound',
          'wms.count',
          'wms.warehouses'
        )
        """
    )

    # 4) 还原复用的旧一级页：wms.inbound / wms.inventory
    op.execute(
        """
        UPDATE page_registry
        SET
          name = '入库',
          parent_code = NULL,
          level = 1,
          domain_code = 'wms',
          show_in_topbar = TRUE,
          show_in_sidebar = FALSE,
          inherit_permissions = FALSE,
          read_permission_id = (
            SELECT id FROM permissions WHERE name = 'page.wms.inbound.read'
          ),
          write_permission_id = (
            SELECT id FROM permissions WHERE name = 'page.wms.inbound.write'
          ),
          sort_order = 10,
          is_active = TRUE
        WHERE code = 'wms.inbound'
        """
    )

    op.execute(
        """
        UPDATE page_registry
        SET
          name = '库存',
          parent_code = NULL,
          level = 1,
          domain_code = 'wms',
          show_in_topbar = TRUE,
          show_in_sidebar = FALSE,
          inherit_permissions = FALSE,
          read_permission_id = (
            SELECT id FROM permissions WHERE name = 'page.wms.inventory.read'
          ),
          write_permission_id = (
            SELECT id FROM permissions WHERE name = 'page.wms.inventory.write'
          ),
          sort_order = 60,
          is_active = TRUE
        WHERE code = 'wms.inventory'
        """
    )
