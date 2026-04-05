"""de_role_permissions_phase1

Revision ID: 6dbcda2dc5fc
Revises: 708d983562de
Create Date: 2026-04-05 13:27:53.772219

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6dbcda2dc5fc"
down_revision: Union[str, Sequence[str], None] = "708d983562de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_permissions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_user_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_permissions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "permission_id", name="pk_user_permissions"),
    )
    op.create_index(
        "ix_user_permissions_permission_id",
        "user_permissions",
        ["permission_id"],
        unique=False,
    )

    op.create_table(
        "page_registry",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("read_permission_id", sa.Integer(), nullable=False),
        sa.Column("write_permission_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.ForeignKeyConstraint(
            ["read_permission_id"],
            ["permissions.id"],
            name="fk_page_registry_read_permission_id_permissions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["write_permission_id"],
            ["permissions.id"],
            name="fk_page_registry_write_permission_id_permissions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("code", name="pk_page_registry"),
        sa.UniqueConstraint("read_permission_id", name="uq_page_registry_read_permission_id"),
        sa.UniqueConstraint("write_permission_id", name="uq_page_registry_write_permission_id"),
    )

    op.create_table(
        "page_route_prefixes",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("page_code", sa.String(length=64), nullable=False),
        sa.Column("route_prefix", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.ForeignKeyConstraint(
            ["page_code"],
            ["page_registry.code"],
            name="fk_page_route_prefixes_page_code_page_registry",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_page_route_prefixes"),
        sa.UniqueConstraint("route_prefix", name="uq_page_route_prefixes_route_prefix"),
    )
    op.create_index(
        "ix_page_route_prefixes_page_code",
        "page_route_prefixes",
        ["page_code"],
        unique=False,
    )

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

    op.execute(
        """
        INSERT INTO page_registry (code, name, read_permission_id, write_permission_id, sort_order, is_active)
        SELECT *
        FROM (
          SELECT
            'wms.inbound'::varchar(64),
            '入库'::varchar(64),
            (SELECT id FROM permissions WHERE name = 'page.wms.inbound.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.inbound.write'),
            10,
            TRUE
          UNION ALL
          SELECT
            'wms.order_outbound',
            '订单出库',
            (SELECT id FROM permissions WHERE name = 'page.wms.order_outbound.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.order_outbound.write'),
            20,
            TRUE
          UNION ALL
          SELECT
            'wms.order_management',
            '订单管理',
            (SELECT id FROM permissions WHERE name = 'page.wms.order_management.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.order_management.write'),
            30,
            TRUE
          UNION ALL
          SELECT
            'wms.logistics',
            '物流',
            (SELECT id FROM permissions WHERE name = 'page.wms.logistics.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.logistics.write'),
            40,
            TRUE
          UNION ALL
          SELECT
            'wms.internal_ops',
            '仓内作业',
            (SELECT id FROM permissions WHERE name = 'page.wms.internal_ops.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.internal_ops.write'),
            50,
            TRUE
          UNION ALL
          SELECT
            'wms.inventory',
            '库存',
            (SELECT id FROM permissions WHERE name = 'page.wms.inventory.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.inventory.write'),
            60,
            TRUE
          UNION ALL
          SELECT
            'wms.analytics',
            '财务分析',
            (SELECT id FROM permissions WHERE name = 'page.wms.analytics.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.analytics.write'),
            70,
            TRUE
          UNION ALL
          SELECT
            'wms.masterdata',
            '主数据',
            (SELECT id FROM permissions WHERE name = 'page.wms.masterdata.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.masterdata.write'),
            80,
            TRUE
        ) t
        ON CONFLICT (code) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO page_route_prefixes (page_code, route_prefix, sort_order, is_active)
        VALUES
          ('wms.inbound', '/purchase-orders', 10, TRUE),
          ('wms.inbound', '/inbound', 20, TRUE),

          ('wms.order_outbound', '/outbound/pick-tasks', 10, TRUE),
          ('wms.order_outbound', '/outbound/dashboard', 20, TRUE),

          ('wms.order_management', '/oms/pdd/stores', 10, TRUE),
          ('wms.order_management', '/oms/pdd/orders', 20, TRUE),
          ('wms.order_management', '/oms/taobao/stores', 30, TRUE),
          ('wms.order_management', '/oms/taobao/orders', 40, TRUE),
          ('wms.order_management', '/oms/jd/stores', 50, TRUE),
          ('wms.order_management', '/oms/jd/orders', 60, TRUE),

          ('wms.logistics', '/tms/shipment-prepare', 10, TRUE),
          ('wms.logistics', '/tms/dispatch', 20, TRUE),
          ('wms.logistics', '/tms/providers', 30, TRUE),
          ('wms.logistics', '/tms/waybill-configs', 40, TRUE),
          ('wms.logistics', '/tms/pricing', 50, TRUE),
          ('wms.logistics', '/tms/templates', 60, TRUE),
          ('wms.logistics', '/tms/records', 70, TRUE),
          ('wms.logistics', '/tms/billing/items', 80, TRUE),
          ('wms.logistics', '/tms/reconciliation', 90, TRUE),
          ('wms.logistics', '/tms/reports', 100, TRUE),

          ('wms.internal_ops', '/count', 10, TRUE),
          ('wms.internal_ops', '/outbound/internal-outbound', 20, TRUE),

          ('wms.inventory', '/snapshot', 10, TRUE),
          ('wms.inventory', '/inventory/ledger', 20, TRUE),

          ('wms.analytics', '/finance', 10, TRUE),

          ('wms.masterdata', '/items', 10, TRUE),
          ('wms.masterdata', '/warehouses', 20, TRUE),
          ('wms.masterdata', '/suppliers', 30, TRUE)
        ON CONFLICT (route_prefix) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO user_permissions (user_id, permission_id)
        SELECT DISTINCT x.user_id, x.permission_id
        FROM (
          SELECT u.id AS user_id, rp.permission_id
          FROM users u
          JOIN role_permissions rp ON rp.role_id = u.primary_role_id
          WHERE u.primary_role_id IS NOT NULL

          UNION

          SELECT ur.user_id AS user_id, rp.permission_id
          FROM user_roles ur
          JOIN role_permissions rp ON rp.role_id = ur.role_id
        ) x
        ON CONFLICT (user_id, permission_id) DO NOTHING
        """
    )

    op.execute(
        """
        WITH grant_map(old_name, new_name) AS (
          VALUES
            ('purchase.manage', 'page.wms.inbound.read'),
            ('purchase.manage', 'page.wms.inbound.write'),
            ('purchase.report', 'page.wms.inbound.read'),
            ('operations.inbound', 'page.wms.inbound.read'),
            ('operations.inbound', 'page.wms.inbound.write'),

            ('operations.outbound', 'page.wms.order_outbound.read'),
            ('operations.outbound', 'page.wms.order_outbound.write'),
            ('report.outbound', 'page.wms.order_outbound.read'),

            ('config.store.read', 'page.wms.order_management.read'),
            ('config.store.write', 'page.wms.order_management.read'),
            ('config.store.write', 'page.wms.order_management.write'),
            ('operations.outbound', 'page.wms.order_management.read'),
            ('operations.outbound', 'page.wms.order_management.write'),

            ('operations.outbound', 'page.wms.logistics.read'),
            ('operations.outbound', 'page.wms.logistics.write'),
            ('report.outbound', 'page.wms.logistics.read'),
            ('config.store.read', 'page.wms.logistics.read'),
            ('config.store.write', 'page.wms.logistics.read'),
            ('config.store.write', 'page.wms.logistics.write'),
            ('config.shipping_provider.read', 'page.wms.logistics.read'),
            ('config.shipping_provider.write', 'page.wms.logistics.read'),
            ('config.shipping_provider.write', 'page.wms.logistics.write'),

            ('operations.count', 'page.wms.internal_ops.read'),
            ('operations.count', 'page.wms.internal_ops.write'),
            ('operations.internal_outbound', 'page.wms.internal_ops.read'),
            ('operations.internal_outbound', 'page.wms.internal_ops.write'),

            ('report.inventory', 'page.wms.inventory.read'),

            ('report.finance', 'page.wms.analytics.read'),

            ('config.item.read', 'page.wms.masterdata.read'),
            ('config.item.write', 'page.wms.masterdata.read'),
            ('config.item.write', 'page.wms.masterdata.write'),
            ('config.warehouse.read', 'page.wms.masterdata.read'),
            ('config.warehouse.write', 'page.wms.masterdata.read'),
            ('config.warehouse.write', 'page.wms.masterdata.write'),
            ('config.supplier.read', 'page.wms.masterdata.read'),
            ('config.supplier.write', 'page.wms.masterdata.read'),
            ('config.supplier.write', 'page.wms.masterdata.write')
        )
        INSERT INTO user_permissions (user_id, permission_id)
        SELECT DISTINCT up.user_id, p_new.id
        FROM user_permissions up
        JOIN permissions p_old
          ON p_old.id = up.permission_id
        JOIN grant_map gm
          ON gm.old_name = p_old.name
        JOIN permissions p_new
          ON p_new.name = gm.new_name
        ON CONFLICT (user_id, permission_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_page_route_prefixes_page_code", table_name="page_route_prefixes")
    op.drop_table("page_route_prefixes")
    op.drop_table("page_registry")

    op.drop_index("ix_user_permissions_permission_id", table_name="user_permissions")
    op.drop_table("user_permissions")

    op.execute("DELETE FROM permissions WHERE name LIKE 'page.wms.%'")
