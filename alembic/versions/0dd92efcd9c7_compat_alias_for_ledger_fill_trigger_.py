"""compat alias for ledger fill trigger/function (stock_ledger_fill_item_id)

Revision ID: 0dd92efcd9c7
Revises: 6ed238c327cd
Create Date: 2025-11-10 12:02:27.405573
"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0dd92efcd9c7"
down_revision: Union[str, Sequence[str], None] = "6ed238c327cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 兼容函数：stock_ledger_fill_item_id() —— 与 stock_ledger_fill_dims() 等价
    op.execute(
        """
        CREATE OR REPLACE FUNCTION stock_ledger_fill_item_id() RETURNS TRIGGER AS $$
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

    # 兼容触发器：trg_stock_ledger_fill_item_id
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_stock_ledger_fill_item_id ON stock_ledger;
        CREATE TRIGGER trg_stock_ledger_fill_item_id
          BEFORE INSERT ON stock_ledger
          FOR EACH ROW
          EXECUTE FUNCTION stock_ledger_fill_item_id();
        """
    )


def downgrade() -> None:
    # 回滚兼容名（保留上一修订创建的正式函数/触发器）
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_stock_ledger_fill_item_id ON stock_ledger;
        DROP FUNCTION IF EXISTS stock_ledger_fill_item_id();
        """
    )
