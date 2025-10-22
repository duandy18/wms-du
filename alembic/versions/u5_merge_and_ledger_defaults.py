"""merge heads + stock_ledger defaults & trigger

- Merge multiple heads (u4_event_error_log_shop_id, u0_widen_alembic_version_num)
- Add DEFAULT 'ADJUST' for stock_ledger.reason (kept NOT NULL)
- Add BEFORE INSERT trigger to backfill item_id from stocks when NULL

Revision ID: u5_merge_and_ledger_defaults
Revises: u4_event_error_log_shop_id, u0_widen_alembic_version_num
Create Date: 2025-10-21
"""
from alembic import op
import sqlalchemy as sa

# --- Alembic identifiers ---
revision = "u5_merge_and_ledger_defaults"
down_revision = ("u4_event_error_log_shop_id", "u0_widen_alembic_version_num")
branch_labels = None
depends_on = None


def upgrade():
    # 1) reason 默认值：'ADJUST'（保持 NOT NULL，不改空值）
    op.execute("""
        ALTER TABLE stock_ledger
        ALTER COLUMN reason SET DEFAULT 'ADJUST'
    """)

    # 2) occurred_at 有默认值更合理（若你已有 DEFAULT NOW() 可删掉这行）
    op.execute("""
        ALTER TABLE stock_ledger
        ALTER COLUMN occurred_at SET DEFAULT NOW()
    """)

    # 3) BEFORE INSERT 触发器：若 item_id 为空，则从 stocks 回填
    op.execute("""
    CREATE OR REPLACE FUNCTION stock_ledger_bi_fill_item()
    RETURNS TRIGGER AS $$
    DECLARE v_item_id INT;
    BEGIN
        IF NEW.item_id IS NULL THEN
            SELECT s.item_id INTO v_item_id FROM stocks s WHERE s.id = NEW.stock_id;
            NEW.item_id := v_item_id;
        END IF;

        IF NEW.reason IS NULL THEN
            NEW.reason := 'ADJUST';
        END IF;

        IF NEW.occurred_at IS NULL THEN
            NEW.occurred_at := NOW();
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
    # 回退触发器
    op.execute("""
        DROP TRIGGER IF EXISTS trg_stock_ledger_bi_fill_item ON stock_ledger;
        DROP FUNCTION IF EXISTS stock_ledger_bi_fill_item();
    """)

    # 回退默认值（根据你的历史自行调整；这里简单清除）
    op.execute("""
        ALTER TABLE stock_ledger
        ALTER COLUMN reason DROP DEFAULT
    """)
    op.execute("""
        ALTER TABLE stock_ledger
        ALTER COLUMN occurred_at DROP DEFAULT
    """)
