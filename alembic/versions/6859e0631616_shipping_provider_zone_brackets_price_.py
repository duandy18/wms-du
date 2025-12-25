"""shipping_provider_zone_brackets_price_json_mirror

Revision ID: 6859e0631616
Revises: f7954e3232b5
Create Date: 2025-12-21 14:51:35.618170

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "6859e0631616"
down_revision: Union[str, Sequence[str], None] = "f7954e3232b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_zone_brackets"
FUNC = "spzb_sync_price_json"
TRIGGER = "trg_spzb_sync_price_json"


def upgrade() -> None:
    """Upgrade schema."""

    # 1) Add mirror column (nullable first; we will backfill then set NOT NULL)
    op.add_column(
        TABLE,
        sa.Column("price_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # 2) Create a DB-side sync function:
    #    On INSERT/UPDATE it regenerates price_json from structured columns,
    #    so the rest of the system (API/FE) can rely on mirror always being complete.
    op.execute(
        f"""
CREATE OR REPLACE FUNCTION public.{FUNC}() RETURNS trigger AS $$
BEGIN
  IF NEW.pricing_mode = 'flat' THEN
    NEW.price_json := jsonb_build_object(
      'kind', 'flat',
      'amount', COALESCE(NEW.flat_amount, 0)
    );
  ELSIF NEW.pricing_mode = 'linear_total' THEN
    NEW.price_json := jsonb_build_object(
      'kind', 'linear_total',
      'base_amount', COALESCE(NEW.base_amount, 0),
      'rate_per_kg', COALESCE(NEW.rate_per_kg, 0)
    );
  ELSIF NEW.pricing_mode = 'manual_quote' THEN
    NEW.price_json := jsonb_build_object(
      'kind', 'manual_quote',
      'message', 'manual quote required'
    );
  ELSE
    -- Fallback: keep existing, but avoid NULL
    NEW.price_json := COALESCE(NEW.price_json, '{{}}'::jsonb);
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
    )

    # 3) Create trigger:
    #    - BEFORE INSERT: always set price_json
    #    - BEFORE UPDATE of structured columns: keep mirror in sync
    op.execute(
        f"""
DROP TRIGGER IF EXISTS {TRIGGER} ON public.{TABLE};
CREATE TRIGGER {TRIGGER}
BEFORE INSERT OR UPDATE OF pricing_mode, flat_amount, base_amount, rate_per_kg
ON public.{TABLE}
FOR EACH ROW
EXECUTE FUNCTION public.{FUNC}();
"""
    )

    # 4) Backfill existing rows by forcing an UPDATE that fires the trigger
    #    (update a watched column to itself)
    op.execute(
        f"""
UPDATE public.{TABLE}
SET pricing_mode = pricing_mode;
"""
    )

    # 5) Now enforce NOT NULL (after backfill)
    op.alter_column(TABLE, "price_json", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=False)

    # 6) Add CHECK constraints to make the contract explicit and future-proof.
    #    (Trigger already maintains it, CHECK ensures nothing can bypass it)
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


def downgrade() -> None:
    """Downgrade schema."""

    # Drop CHECK constraints
    op.drop_constraint("ck_spzb_price_json_manual_complete", TABLE, type_="check")
    op.drop_constraint("ck_spzb_price_json_linear_complete", TABLE, type_="check")
    op.drop_constraint("ck_spzb_price_json_flat_complete", TABLE, type_="check")

    # Drop trigger + function
    op.execute(f"DROP TRIGGER IF EXISTS {TRIGGER} ON public.{TABLE};")
    op.execute(f"DROP FUNCTION IF EXISTS public.{FUNC}();")

    # Drop column
    op.drop_column(TABLE, "price_json")
