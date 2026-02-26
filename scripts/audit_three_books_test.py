# scripts/audit_three_books_test.py
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text


def _get_dsn() -> str:
    dsn = (os.getenv("WMS_TEST_DATABASE_URL") or os.getenv("WMS_DATABASE_URL") or "").strip()
    if not dsn:
        raise RuntimeError("WMS_TEST_DATABASE_URL / WMS_DATABASE_URL is empty")
    return dsn


def main() -> int:
    dsn = _get_dsn()
    eng = create_engine(dsn, future=True)

    check_sql = text(
        """
        WITH ledger AS (
          SELECT warehouse_id, item_id, lot_id_key, COALESCE(SUM(delta),0) AS ledger_qty
            FROM stock_ledger
           GROUP BY warehouse_id, item_id, lot_id_key
        ),
        bal AS (
          SELECT warehouse_id, item_id, lot_id_key, COALESCE(SUM(qty),0) AS bal_qty
            FROM stocks_lot
           GROUP BY warehouse_id, item_id, lot_id_key
        ),
        j AS (
          SELECT
            COALESCE(b.warehouse_id, l.warehouse_id) AS warehouse_id,
            COALESCE(b.item_id, l.item_id) AS item_id,
            COALESCE(b.lot_id_key, l.lot_id_key) AS lot_id_key,
            COALESCE(l.ledger_qty, 0) AS ledger_qty,
            COALESCE(b.bal_qty, 0) AS bal_qty
          FROM bal b
          FULL JOIN ledger l
            ON l.warehouse_id=b.warehouse_id AND l.item_id=b.item_id AND l.lot_id_key=b.lot_id_key
        )
        SELECT warehouse_id, item_id, lot_id_key, ledger_qty, bal_qty
          FROM j
         WHERE ledger_qty <> bal_qty
         ORDER BY warehouse_id, item_id, lot_id_key
         LIMIT 50
        """
    )

    with eng.begin() as conn:
        rows = conn.execute(check_sql).fetchall()

    print(f"[audit-three-books] dsn={dsn}")
    if rows:
        print("[audit-three-books] FAIL: ledger sums != stocks_lot balances (first 50):")
        for r in rows:
            print(f"  warehouse_id={r[0]} item_id={r[1]} lot_id_key={r[2]} ledger_qty={r[3]} bal_qty={r[4]}")
        return 2

    print("[audit-three-books] OK: Σ(stock_ledger.delta) == stocks_lot.qty for all keys.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"[audit-three-books] FATAL: {e}", file=sys.stderr)
        raise
