"""oms_platform_order_mirrors

Revision ID: 202604281620
Revises: 202604281430
Create Date: 2026-04-28 16:20:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "202604281620"
down_revision: Union[str, Sequence[str], None] = "202604281430"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_platform_tables(platform: str) -> None:
    op.execute(
        f"""
        CREATE TABLE oms_{platform}_order_mirrors (
          id BIGSERIAL PRIMARY KEY,

          collector_order_id BIGINT NOT NULL,
          collector_store_id BIGINT NOT NULL,
          collector_store_code VARCHAR(128) NOT NULL,
          collector_store_name VARCHAR(255) NOT NULL,

          wms_store_id BIGINT NULL REFERENCES stores(id) ON DELETE SET NULL,

          platform_order_no VARCHAR(128) NOT NULL,
          platform_status VARCHAR(64) NULL,

          import_status VARCHAR(32) NOT NULL DEFAULT 'imported',
          mirror_status VARCHAR(32) NOT NULL DEFAULT 'active',

          source_updated_at TIMESTAMPTZ NULL,
          pulled_at TIMESTAMPTZ NULL,
          collector_last_synced_at TIMESTAMPTZ NULL,

          receiver_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
          amounts_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
          platform_fields_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
          raw_refs_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,

          imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

          CONSTRAINT uq_oms_{platform}_order_mirrors_collector_order
            UNIQUE (collector_order_id),
          CONSTRAINT uq_oms_{platform}_order_mirrors_collector_store_order
            UNIQUE (collector_store_id, platform_order_no),
          CONSTRAINT ck_oms_{platform}_order_mirrors_import_status
            CHECK (import_status IN ('imported', 'rejected', 'superseded')),
          CONSTRAINT ck_oms_{platform}_order_mirrors_mirror_status
            CHECK (mirror_status IN ('active', 'archived'))
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE oms_{platform}_order_mirror_lines (
          id BIGSERIAL PRIMARY KEY,

          mirror_id BIGINT NOT NULL REFERENCES oms_{platform}_order_mirrors(id) ON DELETE CASCADE,
          collector_line_id BIGINT NOT NULL,
          collector_order_id BIGINT NOT NULL,
          platform_order_no VARCHAR(128) NOT NULL,

          merchant_sku VARCHAR(128) NULL,
          platform_item_id VARCHAR(128) NULL,
          platform_sku_id VARCHAR(128) NULL,
          title VARCHAR(255) NULL,

          quantity NUMERIC(14, 4) NOT NULL DEFAULT 0,
          unit_price NUMERIC(14, 2) NULL,
          line_amount NUMERIC(14, 2) NULL,

          platform_fields_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
          raw_item_payload_json JSONB NULL,

          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

          CONSTRAINT uq_oms_{platform}_order_mirror_lines_line
            UNIQUE (mirror_id, collector_line_id)
        )
        """
    )

    op.execute(
        f"CREATE INDEX ix_oms_{platform}_order_mirrors_order_no "
        f"ON oms_{platform}_order_mirrors(platform_order_no)"
    )
    op.execute(
        f"CREATE INDEX ix_oms_{platform}_order_mirrors_status "
        f"ON oms_{platform}_order_mirrors(platform_status)"
    )
    op.execute(
        f"CREATE INDEX ix_oms_{platform}_order_mirrors_wms_store "
        f"ON oms_{platform}_order_mirrors(wms_store_id)"
    )
    op.execute(
        f"CREATE INDEX ix_oms_{platform}_order_mirror_lines_mirror "
        f"ON oms_{platform}_order_mirror_lines(mirror_id)"
    )
    op.execute(
        f"CREATE INDEX ix_oms_{platform}_order_mirror_lines_merchant_sku "
        f"ON oms_{platform}_order_mirror_lines(merchant_sku)"
    )


def upgrade() -> None:
    """Upgrade schema."""

    for platform in ("pdd", "taobao", "jd"):
        _create_platform_tables(platform)


def downgrade() -> None:
    """Downgrade schema."""

    for platform in ("jd", "taobao", "pdd"):
        op.execute(f"DROP TABLE IF EXISTS oms_{platform}_order_mirror_lines")
        op.execute(f"DROP TABLE IF EXISTS oms_{platform}_order_mirrors")
