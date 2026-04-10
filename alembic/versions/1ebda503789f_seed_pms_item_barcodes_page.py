"""seed_pms_item_barcodes_page

Revision ID: 1ebda503789f
Revises: 32b08d41971c
Create Date: 2026-04-09 21:37:15.802489

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1ebda503789f"
down_revision: Union[str, Sequence[str], None] = "32b08d41971c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

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
          'pms.item_barcodes',
          '商品条码',
          'pms',
          2,
          'pms',
          FALSE,
          TRUE,
          TRUE,
          NULL,
          NULL,
          15,
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

    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES (
          'pms.item_barcodes',
          '/item-barcodes',
          10,
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
        WHERE route_prefix = '/item-barcodes'
           OR page_code = 'pms.item_barcodes'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'pms.item_barcodes'
        """
    )
