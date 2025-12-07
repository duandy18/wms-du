"""add stock_ledger fill-dims trigger (item_id/location_id from stocks)

Revision ID: 6ed238c327cd
Revises: a64b5b5ec168
Create Date: 2025-11-10 11:58:08.501121
"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6ed238c327cd"
down_revision: Union[str, Sequence[str], None] = "a64b5b5ec168"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 兜底函数：在 INSERT 之前用 stocks 补齐缺失的 item_id / location_id
    op.execute(
        """
        CREATE OR REPLACE FUNCTION stock_ledger_fill_dims() RETURNS TRIGGER AS $$
        DECLARE s_item int; s_loc int;
        BEGIN
          IF NEW.item_id IS NULL OR NEW.location_id IS NULL THEN
            SELECT item_id, location_id INTO s_item, s_loc
              FROM stocks WHERE id = NEW.stock_id;
            IF NEW.item_id IS NULL THEN
              NEW.item_id := s_item;
            END IF;
            IF NEW.location_id IS NULL THEN
              NEW.location_id := s_loc;
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # 2) 触发器：每条 INSERT 前触发
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_stock_ledger_fill_dims ON stock_ledger;
        CREATE TRIGGER trg_stock_ledger_fill_dims
          BEFORE INSERT ON stock_ledger
          FOR EACH ROW
          EXECUTE FUNCTION stock_ledger_fill_dims();
        """
    )

    # 3) 历史数据一次性回填（幂等）
    op.execute(
        """
        UPDATE stock_ledger l
           SET item_id = COALESCE(l.item_id, s.item_id),
               location_id = COALESCE(l.location_id, s.location_id)
          FROM stocks s
         WHERE l.stock_id = s.id
           AND (l.item_id IS NULL OR l.location_id IS NULL);
        """
    )

    # 4) （可选）后续稳定后可收紧约束为 NOT NULL：
    # op.execute("ALTER TABLE stock_ledger ALTER COLUMN item_id SET NOT NULL;")
    # op.execute("ALTER TABLE stock_ledger ALTER COLUMN location_id SET NOT NULL;")


def downgrade() -> None:
    # 回滚触发器与函数
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_stock_ledger_fill_dims ON stock_ledger;
        DROP FUNCTION IF EXISTS stock_ledger_fill_dims();
        """
    )
