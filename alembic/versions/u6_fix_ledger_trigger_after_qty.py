"""fix: stock_ledger trigger also fills after_qty

- Update BEFORE INSERT trigger to backfill `after_qty` as (stocks.qty + NEW.delta)
  when NEW.after_qty is NULL.
- Keep reason default, occurred_at default, and item_id backfill behavior.

Revision ID: u6_fix_ledger_trigger_after_qty
Revises: u5_merge_and_ledger_defaults
Create Date: 2025-10-21
"""

from alembic import op

# --- Alembic identifiers ---
revision = "u6_fix_ledger_trigger_after_qty"
down_revision = "u5_merge_and_ledger_defaults"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE OR REPLACE FUNCTION stock_ledger_bi_fill_item()
        RETURNS TRIGGER AS $$
        DECLARE
            v_item_id INT;
            v_qty     INT;
        BEGIN
            -- 回填 item_id
            IF NEW.item_id IS NULL THEN
                SELECT s.item_id INTO v_item_id
                FROM stocks s
                WHERE s.id = NEW.stock_id;
                NEW.item_id := v_item_id;
            END IF;

            -- 默认 reason / occurred_at
            IF NEW.reason IS NULL THEN
                NEW.reason := 'ADJUST';
            END IF;

            IF NEW.occurred_at IS NULL THEN
                NEW.occurred_at := NOW();
            END IF;

            -- 回填 after_qty = 当前库存 + delta（若 NEW.after_qty 未显式给出）
            IF NEW.after_qty IS NULL THEN
                SELECT s.qty INTO v_qty
                FROM stocks s
                WHERE s.id = NEW.stock_id;
                NEW.after_qty := COALESCE(v_qty, 0) + COALESCE(NEW.delta, 0);
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_stock_ledger_bi_fill_item ON stock_ledger;

        CREATE TRIGGER trg_stock_ledger_bi_fill_item
        BEFORE INSERT ON stock_ledger
        FOR EACH ROW
        EXECUTE FUNCTION stock_ledger_bi_fill_item();
        """
    )


def downgrade():
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_stock_ledger_bi_fill_item ON stock_ledger;
        DROP FUNCTION IF EXISTS stock_ledger_bi_fill_item();
        """
    )
