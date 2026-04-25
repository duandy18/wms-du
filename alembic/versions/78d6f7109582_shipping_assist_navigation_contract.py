"""shipping assist navigation contract

Revision ID: 78d6f7109582
Revises: 2a8be0e16db9
Create Date: 2026-04-25 19:18:50.700830

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "78d6f7109582"
down_revision: Union[str, Sequence[str], None] = "2a8be0e16db9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 先删旧 /tms route_prefix。
    # page_route_prefixes.page_code 引用 page_registry.code，必须先移除旧映射，
    # 否则后续把 tms.* page_code 改名为 shipping_assist.* 时会被外键挡住。
    op.execute(
        """
        DELETE FROM page_route_prefixes
         WHERE route_prefix LIKE '/tms/%'
            OR page_code = 'tms'
            OR page_code LIKE 'tms.%'
        """
    )

    # 2) 权限名改为终态合同：page.shipping_assist.*
    # 只改 permissions.name，不改 permission id，因此 user_permissions 与 page_registry 外键不需要重挂。
    op.execute(
        """
        UPDATE permissions
           SET name = 'page.shipping_assist.read'
         WHERE name = 'page.tms.read'
        """
    )
    op.execute(
        """
        UPDATE permissions
           SET name = 'page.shipping_assist.write'
         WHERE name = 'page.tms.write'
        """
    )

    # 3) 先移除 domain_code 旧约束，再迁移 page_registry 数据。
    # 不能先加只允许 shipping_assist 的约束，否则当前仍存在 domain_code='tms' 的行会校验失败。
    op.execute(
        """
        ALTER TABLE page_registry
        DROP CONSTRAINT IF EXISTS ck_page_registry_domain_code
        """
    )

    # 4) page_registry code 从 tms.* 改为 shipping_assist.*。
    op.execute(
        """
        UPDATE page_registry
           SET code = regexp_replace(code, '^tms', 'shipping_assist'),
               parent_code = CASE
                 WHEN parent_code IS NULL THEN NULL
                 ELSE regexp_replace(parent_code, '^tms', 'shipping_assist')
               END,
               domain_code = 'shipping_assist'
         WHERE code = 'tms'
            OR code LIKE 'tms.%'
        """
    )

    # 5) 添加终态 domain_code 约束，不再允许 tms。
    op.execute(
        """
        ALTER TABLE page_registry
        ADD CONSTRAINT ck_page_registry_domain_code
        CHECK (domain_code IN (
          'analytics',
          'oms',
          'pms',
          'procurement',
          'wms',
          'shipping_assist',
          'admin',
          'inbound'
        ))
        """
    )

    # 6) 插入终态页面 URL。这里不保留 /tms alias。
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          route_prefix,
          page_code,
          sort_order,
          is_active
        )
        VALUES
          ('/shipping-assist/shipping/quote', 'shipping_assist.shipping.quote', 10, TRUE),
          ('/shipping-assist/shipping/records', 'shipping_assist.shipping.records', 20, TRUE),

          ('/shipping-assist/pricing/providers', 'shipping_assist.pricing.providers', 30, TRUE),
          ('/shipping-assist/pricing/bindings', 'shipping_assist.pricing.bindings', 40, TRUE),
          ('/shipping-assist/pricing/templates', 'shipping_assist.pricing.templates', 50, TRUE),

          ('/shipping-assist/billing/items', 'shipping_assist.billing.items', 60, TRUE),
          ('/shipping-assist/billing/reconciliation', 'shipping_assist.billing.reconciliation', 70, TRUE),

          ('/shipping-assist/settings/waybill', 'shipping_assist.settings.waybill', 80, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 先删终态 route_prefix，避免 page_code 外键挡住 page_registry 改名。
    op.execute(
        """
        DELETE FROM page_route_prefixes
         WHERE route_prefix LIKE '/shipping-assist/%'
            OR page_code = 'shipping_assist'
            OR page_code LIKE 'shipping_assist.%'
        """
    )

    # 2) 先移除只允许 shipping_assist 的约束，再把 domain_code 改回 tms。
    op.execute(
        """
        ALTER TABLE page_registry
        DROP CONSTRAINT IF EXISTS ck_page_registry_domain_code
        """
    )

    # 3) page_registry code 退回 tms.*。
    op.execute(
        """
        UPDATE page_registry
           SET code = regexp_replace(code, '^shipping_assist', 'tms'),
               parent_code = CASE
                 WHEN parent_code IS NULL THEN NULL
                 ELSE regexp_replace(parent_code, '^shipping_assist', 'tms')
               END,
               domain_code = 'tms'
         WHERE code = 'shipping_assist'
            OR code LIKE 'shipping_assist.%'
        """
    )

    # 4) 恢复 domain_code 约束，退回允许 tms。
    op.execute(
        """
        ALTER TABLE page_registry
        ADD CONSTRAINT ck_page_registry_domain_code
        CHECK (domain_code IN (
          'analytics',
          'oms',
          'pms',
          'procurement',
          'wms',
          'tms',
          'admin',
          'inbound'
        ))
        """
    )

    # 5) 权限名退回 page.tms.*。
    op.execute(
        """
        UPDATE permissions
           SET name = 'page.tms.read'
         WHERE name = 'page.shipping_assist.read'
        """
    )
    op.execute(
        """
        UPDATE permissions
           SET name = 'page.tms.write'
         WHERE name = 'page.shipping_assist.write'
        """
    )

    # 6) 恢复旧 /tms route_prefix。
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          route_prefix,
          page_code,
          sort_order,
          is_active
        )
        VALUES
          ('/tms/shipment-prepare', 'tms.shipping.quote', 10, TRUE),
          ('/tms/dispatch', 'tms.shipping.quote', 20, TRUE),
          ('/tms/records', 'tms.shipping.records', 30, TRUE),
          ('/tms/providers', 'tms.pricing.providers', 40, TRUE),
          ('/tms/pricing', 'tms.pricing.bindings', 50, TRUE),
          ('/tms/templates', 'tms.pricing.templates', 60, TRUE),
          ('/tms/billing/items', 'tms.billing.items', 70, TRUE),
          ('/tms/reconciliation', 'tms.billing.reconciliation', 80, TRUE),
          ('/tms/waybill-configs', 'tms.settings.waybill', 90, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )
