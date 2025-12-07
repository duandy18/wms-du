"""20251203_drop_stocks_legacy_triggers

Revision ID: 11dc33423ea3
Revises: ed0f681f98b2
Create Date: 2025-12-03 14:44:16.698521

这个迁移用于清理 stocks 表上的遗留触发器，它们依赖已经删除的字段
（例如 qty_on_hand），会导致 INSERT/UPDATE 抛 UndefinedColumnError。
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "11dc33423ea3"
down_revision: Union[str, Sequence[str], None] = "ed0f681f98b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy triggers and helper functions on stocks."""
    # 1) 删除 stocks 表上的所有触发器（新架构下不再需要任何 stocks trigger）
    op.execute(
        """
        DO $$
        DECLARE
          r RECORD;
        BEGIN
          FOR r IN
            SELECT tgname
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            WHERE c.relname = 'stocks'
              AND NOT t.tgisinternal
          LOOP
            EXECUTE format('DROP TRIGGER IF EXISTS %I ON stocks;', r.tgname);
          END LOOP;
        END;
        $$;
        """
    )

    # 2) 删除常见的遗留函数（若不存在则无副作用）
    op.execute("DROP FUNCTION IF EXISTS stocks_fill_qty_on_hand();")


def downgrade() -> None:
    """
    如果需要回滚，可以恢复一个“无害”的空壳函数 + 触发器，
    不再访问 qty_on_hand 等已经删除的列，只是简单 RETURN NEW。
    """

    # 恢复一个空函数（不会访问不存在的列）
    op.execute(
        """
        CREATE FUNCTION stocks_fill_qty_on_hand()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            -- Legacy 函数曾经访问 NEW.qty_on_hand 等字段。
            -- 新结构已经移除这些列，这里只原样返回 NEW，避免再次引入旧逻辑。
            RETURN NEW;
        END;
        $$;
        """
    )

    # 恢复一个通用触发器（但逻辑是 no-op）
    op.execute(
        """
        CREATE TRIGGER trg_stocks_fill_qty_on_hand
        BEFORE INSERT OR UPDATE ON stocks
        FOR EACH ROW
        EXECUTE FUNCTION stocks_fill_qty_on_hand();
        """
    )
