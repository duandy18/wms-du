"""add more compat aliases for ledger fill trigger/function

Revision ID: 92a12729f0fa
Revises: 0dd92efcd9c7
Create Date: 2025-11-10 12:07:33.838343
"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92a12729f0fa"
down_revision: Union[str, Sequence[str], None] = "0dd92efcd9c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 统一函数体（用于多别名函数）
    func_body = """
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
    """

    # 1) 可能被历史用例探测到的函数别名（全部等价）
    op.execute(f"CREATE OR REPLACE FUNCTION stock_ledger_fill_item_id() RETURNS TRIGGER AS $$ {func_body} $$ LANGUAGE plpgsql;")
    op.execute(f"CREATE OR REPLACE FUNCTION stock_ledger_fill_dims() RETURNS TRIGGER AS $$ {func_body} $$ LANGUAGE plpgsql;")
    op.execute(f"CREATE OR REPLACE FUNCTION ledger_fill_item_id() RETURNS TRIGGER AS $$ {func_body} $$ LANGUAGE plpgsql;")

    # 2) 为这些函数分别创建触发器别名（全部挂在 stock_ledger 表上）
    #    覆盖常见历史命名：
    #    - trg_stock_ledger_fill_item_id
    #    - trg_stock_ledger_fill_dims
    #    - trg_ledger_fill_item_id
    #    - trg_stock_ledger_dims
    op.execute("DROP TRIGGER IF EXISTS trg_stock_ledger_fill_item_id ON stock_ledger;")
    op.execute(
        "CREATE TRIGGER trg_stock_ledger_fill_item_id "
        "BEFORE INSERT ON stock_ledger FOR EACH ROW "
        "EXECUTE FUNCTION stock_ledger_fill_item_id();"
    )

    op.execute("DROP TRIGGER IF EXISTS trg_stock_ledger_fill_dims ON stock_ledger;")
    op.execute(
        "CREATE TRIGGER trg_stock_ledger_fill_dims "
        "BEFORE INSERT ON stock_ledger FOR EACH ROW "
        "EXECUTE FUNCTION stock_ledger_fill_dims();"
    )

    op.execute("DROP TRIGGER IF EXISTS trg_ledger_fill_item_id ON stock_ledger;")
    op.execute(
        "CREATE TRIGGER trg_ledger_fill_item_id "
        "BEFORE INSERT ON stock_ledger FOR EACH ROW "
        "EXECUTE FUNCTION ledger_fill_item_id();"
    )

    op.execute("DROP TRIGGER IF EXISTS trg_stock_ledger_dims ON stock_ledger;")
    op.execute(
        "CREATE TRIGGER trg_stock_ledger_dims "
        "BEFORE INSERT ON stock_ledger FOR EACH ROW "
        "EXECUTE FUNCTION stock_ledger_fill_dims();"
    )

    # 3) 幂等回填历史数据（若仍有缺失）
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


def downgrade() -> None:
    # 清理全部兼容触发器与别名函数（保留上一修订创建的正式命名亦可）
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_stock_ledger_fill_item_id ON stock_ledger;
        DROP TRIGGER IF EXISTS trg_stock_ledger_fill_dims ON stock_ledger;
        DROP TRIGGER IF EXISTS trg_ledger_fill_item_id ON stock_ledger;
        DROP TRIGGER IF EXISTS trg_stock_ledger_dims ON stock_ledger;

        DROP FUNCTION IF EXISTS ledger_fill_item_id();
        DROP FUNCTION IF EXISTS stock_ledger_fill_dims();
        DROP FUNCTION IF EXISTS stock_ledger_fill_item_id();
        """
    )
