"""guard forbid none batch_code

Revision ID: f78d954e9f38
Revises: edbfc2c46b1b
Create Date: 2026-02-02 00:41:18.973658

目的：
- 防止 batch_code 被错误写入字符串 'None'（通常来自 str(None)）
- 对 stocks / stock_ledger 两张事实表加 CHECK 约束：
    batch_code IS NULL OR lower(batch_code) <> 'none'

注意：
- 这是“防回潮”护栏，不替代 datafix
- upgrade 使用条件执行，避免在不同环境重复执行时报错
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f78d954e9f38"
down_revision: Union[str, Sequence[str], None] = "edbfc2c46b1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # stocks
    conn.exec_driver_sql(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_stocks_batch_code_not_none'
          ) THEN
            ALTER TABLE public.stocks
              ADD CONSTRAINT ck_stocks_batch_code_not_none
              CHECK (batch_code IS NULL OR lower(batch_code) <> 'none');
          END IF;
        END$$;
        """
    )

    # stock_ledger
    conn.exec_driver_sql(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_stock_ledger_batch_code_not_none'
          ) THEN
            ALTER TABLE public.stock_ledger
              ADD CONSTRAINT ck_stock_ledger_batch_code_not_none
              CHECK (batch_code IS NULL OR lower(batch_code) <> 'none');
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.exec_driver_sql(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_stock_ledger_batch_code_not_none'
          ) THEN
            ALTER TABLE public.stock_ledger
              DROP CONSTRAINT ck_stock_ledger_batch_code_not_none;
          END IF;
        END$$;
        """
    )

    conn.exec_driver_sql(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'ck_stocks_batch_code_not_none'
          ) THEN
            ALTER TABLE public.stocks
              DROP CONSTRAINT ck_stocks_batch_code_not_none;
          END IF;
        END$$;
        """
    )
