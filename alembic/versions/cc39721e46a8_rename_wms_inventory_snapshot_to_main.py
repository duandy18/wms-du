"""rename_wms_inventory_snapshot_to_main

Revision ID: cc39721e46a8
Revises: fc982b78117a
Create Date: 2026-04-11 10:36:58.973020

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cc39721e46a8"
down_revision: Union[str, Sequence[str], None] = "fc982b78117a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_CODE = "wms.inventory.snapshot"
NEW_CODE = "wms.inventory.main"

OLD_NAME = "库存快照"
NEW_NAME = "即时库存"

OLD_ROUTE = "/snapshot"
NEW_ROUTE = "/inventory"


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # 1) 复制旧页面到新 code
    conn.execute(
        sa.text(
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
            SELECT
                :new_code,
                :new_name,
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
            FROM page_registry
            WHERE code = :old_code
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
        ),
        {
            "old_code": OLD_CODE,
            "new_code": NEW_CODE,
            "new_name": NEW_NAME,
        },
    )

    # 2) 如有子页挂在旧 code，下挂到新 code
    conn.execute(
        sa.text(
            """
            UPDATE page_registry
               SET parent_code = :new_code
             WHERE parent_code = :old_code
            """
        ),
        {"old_code": OLD_CODE, "new_code": NEW_CODE},
    )

    # 3) route_prefix 先改挂新 page_code
    conn.execute(
        sa.text(
            """
            UPDATE page_route_prefixes
               SET page_code = :new_code
             WHERE page_code = :old_code
            """
        ),
        {"old_code": OLD_CODE, "new_code": NEW_CODE},
    )

    # 4) 主库存页路径从 /snapshot 改成 /inventory
    conn.execute(
        sa.text(
            """
            UPDATE page_route_prefixes
               SET route_prefix = :new_route
             WHERE page_code = :new_code
               AND route_prefix = :old_route
            """
        ),
        {
            "new_code": NEW_CODE,
            "old_route": OLD_ROUTE,
            "new_route": NEW_ROUTE,
        },
    )

    # 5) 删除旧页面 code
    conn.execute(
        sa.text(
            """
            DELETE FROM page_registry
             WHERE code = :old_code
            """
        ),
        {"old_code": OLD_CODE},
    )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()

    # 1) 恢复旧页面 code
    conn.execute(
        sa.text(
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
            SELECT
                :old_code,
                :old_name,
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
            FROM page_registry
            WHERE code = :new_code
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
        ),
        {
            "old_code": OLD_CODE,
            "new_code": NEW_CODE,
            "old_name": OLD_NAME,
        },
    )

    # 2) 如有子页挂在新 code，下挂回旧 code
    conn.execute(
        sa.text(
            """
            UPDATE page_registry
               SET parent_code = :old_code
             WHERE parent_code = :new_code
            """
        ),
        {"old_code": OLD_CODE, "new_code": NEW_CODE},
    )

    # 3) 路由先改回 /snapshot
    conn.execute(
        sa.text(
            """
            UPDATE page_route_prefixes
               SET route_prefix = :old_route
             WHERE page_code = :new_code
               AND route_prefix = :new_route
            """
        ),
        {
            "old_route": OLD_ROUTE,
            "new_route": NEW_ROUTE,
            "new_code": NEW_CODE,
        },
    )

    # 4) route_prefix 再改挂旧 page_code
    conn.execute(
        sa.text(
            """
            UPDATE page_route_prefixes
               SET page_code = :old_code
             WHERE page_code = :new_code
            """
        ),
        {"old_code": OLD_CODE, "new_code": NEW_CODE},
    )

    # 5) 删除新页面 code
    conn.execute(
        sa.text(
            """
            DELETE FROM page_registry
             WHERE code = :new_code
            """
        ),
        {"new_code": NEW_CODE},
    )
