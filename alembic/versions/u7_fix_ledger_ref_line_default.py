"""fix: stock_ledger ref_line default + trigger fill

- Set DEFAULT 1 for stock_ledger.ref_line (kept NOT NULL)
- Update BEFORE INSERT trigger to fill ref_line=1 when NULL

Revision ID: u7_fix_ledger_ref_line_default
Revises: u6_fix_ledger_trigger_after_qty
Create Date: 2025-10-21
"""
from alembic import op
import sqlalchemy as sa

# --- Alembic identifiers ---
revision = "u7_fix_ledger_ref_line_default"
down_revision = "u6_fix_ledger_trigger_after_qty"
branch_labels = None
depends_on = None


def upgrade():
    # 1) ref_line 默认值：1（保持 NOT NULL）
    op.execute("""
        ALTER TABLE stock_ledger
        ALTER COLUMN ref_line SET DEFAULT 1
    """)

    # 2) 触发器追加：若 NEW.ref_line 为空则设为 1
    op.execute("""
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

        -- 若未提供 ref_line，则设为 1（体检用例仅插入 stock_id, delta）
        IF NEW.ref_line IS NULL THEN
            NEW.ref_line := 1;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_stock_ledger_bi_fill_item ON stock_ledger;

    CREATE TRIGGER trg_stock_ledger_bi_fill_item
    BEFORE INSERT ON stock_ledger
    FOR EACH ROW
    EXECUTE FUNCTION stock_ledger_bi_fill_item();
    """)


def downgrade():
    op.execute("""
        DROP TRIGGER IF EXISTS trg_stock_ledger_bi_fill_item ON stock_ledger;
        DROP FUNCTION IF EXISTS stock_ledger_bi_fill_item();
    """)
    op.execute("""
        ALTER TABLE stock_ledger
        ALTER COLUMN ref_line DROP DEFAULT
    """)
