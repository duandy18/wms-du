"""drop_price_json_from_zone_brackets

Revision ID: 45fdd2438bca
Revises: 6a4eea928e55
Create Date: 2026-03-06 11:21:48.844359

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "45fdd2438bca"
down_revision: Union[str, Sequence[str], None] = "6a4eea928e55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_zone_brackets"
FUNC = "spzb_sync_price_json"
TRIGGER = "trg_spzb_sync_price_json"


def upgrade() -> None:
    # 1) 先删除所有依赖 price_json 的 CHECK
    op.execute(
        f"""
        ALTER TABLE {TABLE}
        DROP CONSTRAINT IF EXISTS ck_spzb_price_json_flat_complete
        """
    )
    op.execute(
        f"""
        ALTER TABLE {TABLE}
        DROP CONSTRAINT IF EXISTS ck_spzb_price_json_linear_complete
        """
    )
    op.execute(
        f"""
        ALTER TABLE {TABLE}
        DROP CONSTRAINT IF EXISTS ck_spzb_price_json_manual_complete
        """
    )
    op.execute(
        f"""
        ALTER TABLE {TABLE}
        DROP CONSTRAINT IF EXISTS ck_spzb_price_json_step_over_complete
        """
    )

    # 2) 删除同步 trigger / function
    op.execute(f"DROP TRIGGER IF EXISTS {TRIGGER} ON {TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS public.{FUNC}()")

    # 3) 删除镜像列 price_json
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_column("price_json")


def downgrade() -> None:
    # 1) 恢复 price_json（先 nullable，回填后再 NOT NULL）
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.add_column(
            sa.Column(
                "price_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            )
        )

    # 2) 恢复 DB 侧 mirror function
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION public.{FUNC}() RETURNS trigger AS $$
        BEGIN
          IF NEW.pricing_mode = 'flat' THEN
            NEW.price_json := jsonb_build_object(
              'kind', 'flat',
              'amount', COALESCE(NEW.flat_amount, 0)
            );
            RETURN NEW;
          END IF;

          IF NEW.pricing_mode = 'linear_total' THEN
            NEW.price_json := jsonb_build_object(
              'kind', 'linear_total',
              'base_amount', COALESCE(NEW.base_amount, 0),
              'rate_per_kg', COALESCE(NEW.rate_per_kg, 0)
            );
            RETURN NEW;
          END IF;

          IF NEW.pricing_mode = 'step_over' THEN
            NEW.price_json := jsonb_build_object(
              'kind', 'step_over',
              'base_kg', COALESCE(NEW.base_kg, 0),
              'base_amount', COALESCE(NEW.base_amount, 0),
              'rate_per_kg', COALESCE(NEW.rate_per_kg, 0)
            );
            RETURN NEW;
          END IF;

          NEW.price_json := jsonb_build_object('kind', 'manual_quote');
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # 3) 恢复 trigger
    op.execute(
        f"""
        CREATE TRIGGER {TRIGGER}
        BEFORE INSERT OR UPDATE OF pricing_mode, flat_amount, base_kg, base_amount, rate_per_kg
        ON {TABLE}
        FOR EACH ROW
        EXECUTE FUNCTION public.{FUNC}();
        """
    )

    # 4) 回填现有数据
    op.execute(
        f"""
        UPDATE {TABLE}
        SET pricing_mode = pricing_mode
        """
    )

    # 5) 设回 NOT NULL
    op.alter_column(
        TABLE,
        "price_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )

    # 6) 恢复相关 CHECK
    op.create_check_constraint(
        "ck_spzb_price_json_flat_complete",
        TABLE,
        "(pricing_mode <> 'flat' OR (price_json->>'kind'='flat' AND (price_json ? 'amount')))",
    )
    op.create_check_constraint(
        "ck_spzb_price_json_linear_complete",
        TABLE,
        "(pricing_mode <> 'linear_total' OR (price_json->>'kind'='linear_total' AND (price_json ? 'base_amount') AND (price_json ? 'rate_per_kg')))",
    )
    op.create_check_constraint(
        "ck_spzb_price_json_manual_complete",
        TABLE,
        "(pricing_mode <> 'manual_quote' OR (price_json->>'kind'='manual_quote'))",
    )
    op.create_check_constraint(
        "ck_spzb_price_json_step_over_complete",
        TABLE,
        "(pricing_mode <> 'step_over' OR ((price_json->>'kind')='step_over' AND (price_json ? 'base_kg') AND (price_json ? 'base_amount') AND (price_json ? 'rate_per_kg')))",
    )
