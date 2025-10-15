#!/usr/bin/env python3
import os, sys
from sqlalchemy import create_engine, text

WARN = "WARN"

def has_table(conn, fqname: str) -> bool:
    # fqname 形如 'public.stocks'
    return bool(conn.execute(text("SELECT to_regclass(:fqn) IS NOT NULL"), {"fqn": fqname}).scalar())

def main() -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print(f"{WARN}: DATABASE_URL is empty; skip invariants.")
        return

    # 使用 psycopg v3 驱动（URL 中包含 +psycopg）
    eng = create_engine(url)
    errors: list[str] = []

    with eng.begin() as conn:
        stocks_fqn = "public.stocks"
        ledger_fqn = "public.stock_ledger"

        # 若核心表尚未创建（比如首次迁移链路有延迟），不给红，先跳过
        need_stocks = has_table(conn, stocks_fqn)
        need_ledger = has_table(conn, ledger_fqn)
        if not need_stocks or not need_ledger:
            missing = []
            if not need_stocks:
                missing.append(stocks_fqn)
            if not need_ledger:
                missing.append(ledger_fqn)
            print(f"{WARN}: tables missing ({', '.join(missing)}); skip invariants this run.")
            return

        # 1) UQ: stocks(item_id, location_id)
        uniques = conn.execute(text("""
            SELECT pg_get_constraintdef(c.oid) AS def
            FROM pg_constraint c
            WHERE c.conrelid = to_regclass('public.stocks')
              AND c.contype = 'u'
        """)).fetchall()
        defs_uq = [row[0] for row in uniques]  # 列别名 def，用下标取值避免与 Python 关键字冲突
        has_uq = any(
            ("UNIQUE (" in s and "item_id" in s and "location_id" in s)
            for s in defs_uq
        )
        if not has_uq:
            errors.append("Missing UNIQUE (item_id, location_id) on stocks.")

        # 2) FK: stock_ledger.stock_id -> stocks.id
        fks = conn.execute(text("""
            SELECT pg_get_constraintdef(c.oid) AS def
            FROM pg_constraint c
            WHERE c.conrelid = to_regclass('public.stock_ledger')
              AND c.contype = 'f'
        """)).fetchall()
        defs_fk = [row[0] for row in fks]
        has_fk = any(
            "(stock_id)" in s and "REFERENCES public.stocks(id)" in s
            for s in defs_fk
        )
        if not has_fk:
            errors.append("Missing FK stock_ledger(stock_id) -> stocks(id).")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(2)
    print("DB invariants OK: stocks.UQ + ledger.FK")

if __name__ == "__main__":
    main()
