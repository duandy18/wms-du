# scripts/seed_opening_ledger_test.py
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text


def _get_dsn() -> str:
    dsn = (os.getenv("WMS_TEST_DATABASE_URL") or os.getenv("WMS_DATABASE_URL") or "").strip()
    if not dsn:
        raise RuntimeError("WMS_TEST_DATABASE_URL / WMS_DATABASE_URL is empty")
    # accept psycopg dsn like postgresql+psycopg://...
    return dsn


def main() -> int:
    dsn = _get_dsn()
    eng = create_engine(dsn, future=True)

    ref = os.getenv("OPENING_LEDGER_REF", "OPENING:TEST")
    reason = os.getenv("OPENING_LEDGER_REASON", "OPENING")
    sub_reason = os.getenv("OPENING_LEDGER_SUB_REASON", "OPENING_TEST")

    # 只补“缺口”：diff = bal_qty - ledger_qty
    # 终态口径（Phase M-5）：
    # - 以 (warehouse_id,item_id,lot_id) 为槽位维度（lot-world 余额；lot_id NOT NULL）
    # - stock_ledger 表中没有 batch_code 列；展示码需 JOIN lots 获取
    # - 幂等：依赖 uq_ledger_wh_lot_item_reason_ref_line
    seed_sql = text(
        """
        WITH ledger AS (
          SELECT warehouse_id, item_id, lot_id, COALESCE(SUM(delta),0) AS ledger_qty
            FROM stock_ledger
           GROUP BY warehouse_id, item_id, lot_id
        ),
        bal AS (
          SELECT warehouse_id, item_id, lot_id, COALESCE(SUM(qty),0) AS bal_qty
            FROM stocks_lot
           GROUP BY warehouse_id, item_id, lot_id
        ),
        diff AS (
          SELECT
            b.warehouse_id,
            b.item_id,
            b.lot_id,
            COALESCE(l.ledger_qty, 0) AS ledger_qty,
            b.bal_qty,
            (b.bal_qty - COALESCE(l.ledger_qty, 0)) AS delta_need
          FROM bal b
          LEFT JOIN ledger l
            ON l.warehouse_id=b.warehouse_id AND l.item_id=b.item_id AND l.lot_id=b.lot_id
        ),
        src AS (
          SELECT
            d.warehouse_id,
            d.item_id,
            d.lot_id,
            d.delta_need,
            d.bal_qty AS after_qty
          FROM diff d
          WHERE d.delta_need <> 0
        )
        INSERT INTO stock_ledger(
          reason, after_qty, delta, ref, ref_line, item_id, warehouse_id,
          lot_id, sub_reason
        )
        SELECT
          :reason AS reason,
          s.after_qty AS after_qty,
          s.delta_need AS delta,
          :ref AS ref,
          1 AS ref_line,
          s.item_id,
          s.warehouse_id,
          s.lot_id,
          :sub_reason AS sub_reason
        FROM src s
        ON CONFLICT (reason, ref, ref_line, item_id, warehouse_id, lot_id) DO NOTHING
        """
    )

    check_sql = text(
        """
        WITH ledger AS (
          SELECT warehouse_id, item_id, lot_id, COALESCE(SUM(delta),0) AS ledger_qty
            FROM stock_ledger
           GROUP BY warehouse_id, item_id, lot_id
        ),
        bal AS (
          SELECT warehouse_id, item_id, lot_id, COALESCE(SUM(qty),0) AS bal_qty
            FROM stocks_lot
           GROUP BY warehouse_id, item_id, lot_id
        ),
        j AS (
          SELECT
            COALESCE(b.warehouse_id, l.warehouse_id) AS warehouse_id,
            COALESCE(b.item_id, l.item_id) AS item_id,
            COALESCE(b.lot_id, l.lot_id) AS lot_id,
            COALESCE(l.ledger_qty, 0) AS ledger_qty,
            COALESCE(b.bal_qty, 0) AS bal_qty
          FROM bal b
          FULL JOIN ledger l
            ON l.warehouse_id=b.warehouse_id AND l.item_id=b.item_id AND l.lot_id=b.lot_id
        )
        SELECT warehouse_id, item_id, lot_id, ledger_qty, bal_qty
          FROM j
         WHERE ledger_qty <> bal_qty
         ORDER BY warehouse_id, item_id, lot_id
         LIMIT 50
        """
    )

    with eng.begin() as conn:
        res = conn.execute(seed_sql, {"ref": ref, "reason": reason, "sub_reason": sub_reason})
        inserted = int(getattr(res, "rowcount", 0) or 0)

        remain = conn.execute(check_sql).fetchall()

    print(f"[seed-opening-ledger-test] dsn={dsn}")
    print(f"[seed-opening-ledger-test] inserted_rows={inserted} ref={ref} reason={reason} sub_reason={sub_reason}")
    if remain:
        print("[seed-opening-ledger-test] remaining mismatches (first 50):")
        for r in remain:
            print(f"  warehouse_id={r[0]} item_id={r[1]} lot_id={r[2]} ledger_qty={r[3]} bal_qty={r[4]}")
        # 这里选择非 0 退出，让 CI 直接发现问题（你喜欢硬护栏）
        return 2

    print("[seed-opening-ledger-test] OK: ledger sums match stocks_lot balances.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[seed-opening-ledger-test] FATAL: {e}", file=sys.stderr)
        raise
