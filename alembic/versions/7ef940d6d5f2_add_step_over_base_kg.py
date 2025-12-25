"""add_step_over_base_kg

- Add base_kg to shipping_provider_zone_brackets
- Allow pricing_mode = step_over
- Enforce required fields for step_over
- Extend price_json mirror + trigger

Revision ID: 7ef940d6d5f2
Revises: 25e65824f08a
Create Date: 2025-12-23 13:23:51.147947
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7ef940d6d5f2"
down_revision: Union[str, Sequence[str], None] = "25e65824f08a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 增加 base_kg（首重）
    op.add_column(
        "shipping_provider_zone_brackets",
        sa.Column("base_kg", sa.Numeric(10, 3), nullable=True),
    )

    # 2) 扩展 pricing_mode 枚举：允许 step_over
    op.execute(
        """
        ALTER TABLE shipping_provider_zone_brackets
        DROP CONSTRAINT IF EXISTS ck_spzb_mode_valid
        """
    )
    op.execute(
        """
        ALTER TABLE shipping_provider_zone_brackets
        ADD CONSTRAINT ck_spzb_mode_valid
        CHECK (pricing_mode::text = ANY (ARRAY[
          'flat'::character varying,
          'linear_total'::character varying,
          'step_over'::character varying,
          'manual_quote'::character varying
        ]::text[]))
        """
    )

    # 3) step_over 必须字段校验
    op.execute(
        """
        ALTER TABLE shipping_provider_zone_brackets
        ADD CONSTRAINT ck_spzb_step_over_needs_fields
        CHECK (
          pricing_mode::text <> 'step_over'
          OR (
            base_kg IS NOT NULL
            AND base_amount IS NOT NULL
            AND rate_per_kg IS NOT NULL
          )
        )
        """
    )

    # 4) price_json 镜像完整性（step_over）
    op.execute(
        """
        ALTER TABLE shipping_provider_zone_brackets
        ADD CONSTRAINT ck_spzb_price_json_step_over_complete
        CHECK (
          pricing_mode::text <> 'step_over'
          OR (
            (price_json ->> 'kind') = 'step_over'
            AND price_json ? 'base_kg'
            AND price_json ? 'base_amount'
            AND price_json ? 'rate_per_kg'
          )
        )
        """
    )

    # 5) 更新 price_json 同步触发器
    op.execute(
        """
        CREATE OR REPLACE FUNCTION spzb_sync_price_json()
        RETURNS TRIGGER AS $$
        BEGIN
          IF NEW.pricing_mode = 'flat' THEN
            NEW.price_json := jsonb_build_object(
              'kind','flat',
              'amount', COALESCE(NEW.flat_amount, 0)
            );
            RETURN NEW;
          END IF;

          IF NEW.pricing_mode = 'linear_total' THEN
            NEW.price_json := jsonb_build_object(
              'kind','linear_total',
              'base_amount', COALESCE(NEW.base_amount, 0),
              'rate_per_kg', COALESCE(NEW.rate_per_kg, 0)
            );
            RETURN NEW;
          END IF;

          IF NEW.pricing_mode = 'step_over' THEN
            NEW.price_json := jsonb_build_object(
              'kind','step_over',
              'base_kg', COALESCE(NEW.base_kg, 0),
              'base_amount', COALESCE(NEW.base_amount, 0),
              'rate_per_kg', COALESCE(NEW.rate_per_kg, 0)
            );
            RETURN NEW;
          END IF;

          NEW.price_json := jsonb_build_object('kind','manual_quote');
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_spzb_sync_price_json ON shipping_provider_zone_brackets;
        CREATE TRIGGER trg_spzb_sync_price_json
        BEFORE INSERT OR UPDATE OF pricing_mode, flat_amount, base_kg, base_amount, rate_per_kg
        ON shipping_provider_zone_brackets
        FOR EACH ROW
        EXECUTE FUNCTION spzb_sync_price_json();
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE shipping_provider_zone_brackets DROP CONSTRAINT IF EXISTS ck_spzb_price_json_step_over_complete"
    )
    op.execute(
        "ALTER TABLE shipping_provider_zone_brackets DROP CONSTRAINT IF EXISTS ck_spzb_step_over_needs_fields"
    )

    op.execute(
        "ALTER TABLE shipping_provider_zone_brackets DROP CONSTRAINT IF EXISTS ck_spzb_mode_valid"
    )
    op.execute(
        """
        ALTER TABLE shipping_provider_zone_brackets
        ADD CONSTRAINT ck_spzb_mode_valid
        CHECK (pricing_mode::text = ANY (ARRAY[
          'flat'::character varying,
          'linear_total'::character varying,
          'manual_quote'::character varying
        ]::text[]))
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_spzb_sync_price_json ON shipping_provider_zone_brackets
        """
    )

    op.drop_column("shipping_provider_zone_brackets", "base_kg")
