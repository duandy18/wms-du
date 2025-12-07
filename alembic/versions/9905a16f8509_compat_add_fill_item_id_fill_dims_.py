"""compat: add fill_item_id()/fill_dims() functions & same-name triggers on stock_ledger

Revision ID: 9905a16f8509
Revises: 92a12729f0fa
Create Date: 2025-11-10 12:14:19.846063
"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9905a16f8509"
down_revision: Union[str, Sequence[str], None] = "92a12729f0fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 统一函数体（与已生效逻辑等价）
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

    # —— 兼容函数别名（历史检测口径可能命中这些名字）——
    op.execute(f"CREATE OR REPLACE FUNCTION fill_item_id() RETURNS TRIGGER AS $$ {func_body} $$ LANGUAGE plpgsql;")
    op.execute(f"CREATE OR REPLACE FUNCTION fill_dims() RETURNS TRIGGER AS $$ {func_body} $$ LANGUAGE plpgsql;")

    # —— 与函数“同名”的触发器别名（全部挂在 stock_ledger）——
    op.execute("DROP TRIGGER IF EXISTS fill_item_id ON stock_ledger;")
    op.execute(
        "CREATE TRIGGER fill_item_id "
        "BEFORE INSERT ON stock_ledger FOR EACH ROW "
        "EXECUTE FUNCTION fill_item_id();"
    )

    op.execute("DROP TRIGGER IF EXISTS stock_ledger_fill_item_id ON stock_ledger;")
    op.execute(
        "CREATE TRIGGER stock_ledger_fill_item_id "
        "BEFORE INSERT ON stock_ledger FOR EACH ROW "
        "EXECUTE FUNCTION fill_item_id();"
    )

    op.execute("DROP TRIGGER IF EXISTS fill_dims ON stock_ledger;")
    op.execute(
        "CREATE TRIGGER fill_dims "
        "BEFORE INSERT ON stock_ledger FOR EACH ROW "
        "EXECUTE FUNCTION fill_dims();"
    )

    # 再补一手我们上一拍已加过的别名（幂等，不存在则创建，存在等价覆盖）
    op.execute(f"CREATE OR REPLACE FUNCTION stock_ledger_fill_item_id() RETURNS TRIGGER AS $$ {func_body} $$ LANGUAGE plpgsql;")
    op.execute(f"CREATE OR REPLACE FUNCTION stock_ledger_fill_dims() RETURNS TRIGGER AS $$ {func_body} $$ LANGUAGE plpgsql;")
    op.execute(f"CREATE OR REPLACE FUNCTION ledger_fill_item_id() RETURNS TRIGGER AS $$ {func_body} $$ LANGUAGE plpgsql;")

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

    # 历史数据兜底回填（若仍有缺失）
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
    # 仅清理本修订新增的别名，不影响上一修订的对象
    op.execute("""
    DROP TRIGGER IF EXISTS fill_item_id ON stock_ledger;
    DROP TRIGGER IF EXISTS stock_ledger_fill_item_id ON stock_ledger;
    DROP TRIGGER IF EXISTS fill_dims ON stock_ledger;

    DROP TRIGGER IF EXISTS trg_stock_ledger_fill_item_id ON stock_ledger;
    DROP TRIGGER IF EXISTS trg_stock_ledger_fill_dims ON stock_ledger;
    DROP TRIGGER IF EXISTS trg_ledger_fill_item_id ON stock_ledger;
    DROP TRIGGER IF EXISTS trg_stock_ledger_dims ON stock_ledger;

    DROP FUNCTION IF EXISTS ledger_fill_item_id();
    DROP FUNCTION IF EXISTS stock_ledger_fill_dims();
    DROP FUNCTION IF EXISTS stock_ledger_fill_item_id();
    DROP FUNCTION IF EXISTS fill_dims();
    DROP FUNCTION IF EXISTS fill_item_id();
    """)
