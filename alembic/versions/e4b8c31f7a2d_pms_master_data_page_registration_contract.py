"""pms master data page registration contract

Revision ID: e4b8c31f7a2d
Revises: d8f6a2b41c9e
Create Date: 2026-04-29 20:18:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "e4b8c31f7a2d"
down_revision: Union[str, Sequence[str], None] = "d8f6a2b41c9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """收口 PMS 商品主数据页面树。"""

    op.execute(
        """
        UPDATE page_registry
           SET name = '商品主数据',
               domain_code = 'pms',
               level = 1,
               parent_code = NULL,
               show_in_topbar = TRUE,
               show_in_sidebar = FALSE,
               sort_order = 80,
               is_active = TRUE,
               inherit_permissions = FALSE
         WHERE code = 'pms'
        """
    )

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
          sort_order,
          is_active,
          inherit_permissions,
          read_permission_id,
          write_permission_id
        )
        VALUES
          ('pms.items', '商品列表', 'pms', 2, 'pms', FALSE, TRUE, 10, TRUE, TRUE, NULL, NULL),
          ('pms.brands', '品牌管理', 'pms', 2, 'pms', FALSE, TRUE, 20, TRUE, TRUE, NULL, NULL),
          ('pms.categories', '内部分类', 'pms', 2, 'pms', FALSE, TRUE, 30, TRUE, TRUE, NULL, NULL),
          ('pms.item_attributes', '属性模板', 'pms', 2, 'pms', FALSE, TRUE, 40, TRUE, TRUE, NULL, NULL),
          ('pms.sku_coding', 'SKU编码', 'pms', 2, 'pms', FALSE, TRUE, 50, TRUE, TRUE, NULL, NULL),
          ('pms.item_barcodes', '商品条码', 'pms', 2, 'pms', FALSE, TRUE, 60, TRUE, TRUE, NULL, NULL),
          ('pms.item_uoms', '包装单位', 'pms', 2, 'pms', FALSE, TRUE, 70, TRUE, TRUE, NULL, NULL),
          ('pms.suppliers', '供应商管理', 'pms', 2, 'pms', FALSE, TRUE, 80, TRUE, TRUE, NULL, NULL)
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id
        """
    )

    op.execute(
        """
        UPDATE page_registry
           SET parent_code = 'pms.sku_coding',
               level = 3,
               domain_code = 'pms',
               show_in_topbar = FALSE,
               show_in_sidebar = TRUE,
               is_active = TRUE,
               inherit_permissions = TRUE
         WHERE code IN ('pms.sku_coding.generator', 'pms.sku_coding.dictionaries')
        """
    )

    op.execute(
        """
        INSERT INTO page_route_prefixes (route_prefix, page_code, sort_order, is_active)
        VALUES
          ('/items', 'pms.items', 10, TRUE),
          ('/pms/brands', 'pms.brands', 10, TRUE),
          ('/pms/categories', 'pms.categories', 10, TRUE),
          ('/pms/item-attribute-defs', 'pms.item_attributes', 10, TRUE),
          ('/items/sku-coding/generator', 'pms.sku_coding.generator', 10, TRUE),
          ('/items/sku-coding/dictionaries', 'pms.sku_coding.dictionaries', 20, TRUE),
          ('/item-barcodes', 'pms.item_barcodes', 10, TRUE),
          ('/item-uoms', 'pms.item_uoms', 10, TRUE),
          ('/suppliers', 'pms.suppliers', 10, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
         WHERE code IN (
           'wms.masterdata.items',
           'wms.masterdata.suppliers'
         )
        """
    )


def downgrade() -> None:
    """恢复迁移前 PMS 页面注册。"""

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
          sort_order,
          is_active,
          inherit_permissions,
          read_permission_id,
          write_permission_id
        )
        VALUES
          ('wms.masterdata.suppliers', '供应商管理', 'pms', 2, 'pms', FALSE, TRUE, 30, TRUE, TRUE, NULL, NULL)
        ON CONFLICT (code) DO UPDATE SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id
        """
    )

    op.execute(
        """
        INSERT INTO page_route_prefixes (route_prefix, page_code, sort_order, is_active)
        VALUES ('/suppliers', 'wms.masterdata.suppliers', 10, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    op.execute(
        """
        DELETE FROM page_route_prefixes
         WHERE route_prefix = '/item-uoms'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
         WHERE code IN ('pms.item_uoms', 'pms.suppliers')
        """
    )

    op.execute(
        """
        UPDATE page_registry
           SET sort_order = CASE
             WHEN code = 'pms.items' THEN 10
             WHEN code = 'pms.item_barcodes' THEN 15
             WHEN code = 'pms.item_attributes' THEN 16
             WHEN code = 'pms.sku_coding' THEN 30
             ELSE sort_order
           END
         WHERE code IN ('pms.items', 'pms.item_barcodes', 'pms.item_attributes', 'pms.sku_coding')
        """
    )
