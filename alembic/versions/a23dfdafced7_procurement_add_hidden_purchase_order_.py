# alembic/versions/a23dfdafced7_procurement_add_hidden_purchase_order_.py
"""procurement_add_hidden_purchase_order_detail

Revision ID: a23dfdafced7
Revises: a4a142eb5d71
Create Date: 2026-04-15 19:13:42.242400

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a23dfdafced7"
down_revision: Union[str, Sequence[str], None] = "a4a142eb5d71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 隐藏详情页节点：参与面包屑与路由解析，但不出现在 sidebar/topbar。
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
        VALUES (
          'procurement.purchase_order_detail',
          '查看采购单',
          'procurement',
          2,
          'procurement',
          FALSE,
          FALSE,
          TRUE,
          NULL,
          NULL,
          30,
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

    # 详情页动态路由：
    # 用 chr(58) 生成 ':'，避免 SQLAlchemy 文本把 :poId 识别成绑定参数。
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES (
          'procurement.purchase_order_detail',
          '/purchase-orders/' || chr(58) || 'poId',
          22,
          TRUE
        )
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix = '/purchase-orders/' || chr(58) || 'poId'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'procurement.purchase_order_detail'
        """
    )
