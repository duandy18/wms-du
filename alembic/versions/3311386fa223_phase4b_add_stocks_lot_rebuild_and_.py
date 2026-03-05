"""phase4b add stocks_lot rebuild and reconcile gate

Revision ID: 3311386fa223
Revises: c5092513a21b
Create Date: 2026-02-25 11:35:56.561630

目标：
- 提供可重复 rebuild 的数据库函数（ledger -> stocks_lot）
- 提供对账视图（diff 行为空 = 通过）
- 提供可选断言函数（diff 非空则 RAISE EXCEPTION）

注意：
- 本迁移不自动执行 rebuild，避免迁移阶段大写入/锁表
- rebuild 由发布或运维阶段显式调用
"""

from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3311386fa223"
down_revision: Union[str, Sequence[str], None] = "c5092513a21b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) rebuild 函数（ledger -> stocks_lot，按 lot_id_key 聚合）
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.rebuild_stocks_lot_from_ledger(
          p_reason text DEFAULT 'RECEIPT'
        )
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
          -- stocks_lot 是 ledger 投影，可随时重建
          TRUNCATE TABLE public.stocks_lot;

          INSERT INTO public.stocks_lot (item_id, warehouse_id, lot_id, qty)
          SELECT
            l.item_id,
            l.warehouse_id,
            MAX(l.lot_id) AS lot_id,          -- 同一 lot_id_key 下应一致
            SUM(l.delta)::integer AS qty
          FROM public.stock_ledger l
          WHERE l.reason = p_reason
          GROUP BY l.item_id, l.warehouse_id, l.lot_id_key
          HAVING SUM(l.delta) <> 0;
        END;
        $$;
        """
    )

    # 2) 对账视图（receipt 口径）
    op.execute(
        """
        CREATE OR REPLACE VIEW public.v_stocks_lot_reconcile_receipt AS
        WITH ledger_agg AS (
          SELECT
            item_id,
            warehouse_id,
            lot_id_key,
            SUM(delta)::integer AS qty
          FROM public.stock_ledger
          WHERE reason = 'RECEIPT'
          GROUP BY item_id, warehouse_id, lot_id_key
        ),
        stocks_agg AS (
          SELECT
            item_id,
            warehouse_id,
            lot_id_key,
            SUM(qty)::integer AS qty
          FROM public.stocks_lot
          GROUP BY item_id, warehouse_id, lot_id_key
        )
        SELECT
          COALESCE(s.item_id, a.item_id) AS item_id,
          COALESCE(s.warehouse_id, a.warehouse_id) AS warehouse_id,
          COALESCE(s.lot_id_key, a.lot_id_key) AS lot_id_key,
          COALESCE(s.qty, 0) AS stocks_qty,
          COALESCE(a.qty, 0) AS ledger_qty,
          COALESCE(s.qty, 0) - COALESCE(a.qty, 0) AS diff_qty
        FROM stocks_agg s
        FULL OUTER JOIN ledger_agg a
          ON a.item_id = s.item_id
         AND a.warehouse_id = s.warehouse_id
         AND a.lot_id_key = s.lot_id_key;
        """
    )

    # 3) 断言函数（发现差异则中止）
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.assert_stocks_lot_matches_ledger_receipt()
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        DECLARE bad_count integer;
        BEGIN
          SELECT COUNT(*) INTO bad_count
          FROM public.v_stocks_lot_reconcile_receipt
          WHERE diff_qty <> 0;

          IF bad_count > 0 THEN
            RAISE EXCEPTION
              'stocks_lot reconcile failed: % diff rows (reason=RECEIPT). Inspect v_stocks_lot_reconcile_receipt and run rebuild_stocks_lot_from_ledger().',
              bad_count;
          END IF;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.assert_stocks_lot_matches_ledger_receipt();")
    op.execute("DROP VIEW IF EXISTS public.v_stocks_lot_reconcile_receipt;")
    op.execute("DROP FUNCTION IF EXISTS public.rebuild_stocks_lot_from_ledger(text);")
