#!/usr/bin/env python3
import os, sys
from sqlalchemy import create_engine, text

def main() -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("WARN: DATABASE_URL is empty; skip invariants.")
        return

    # SQLAlchemy 不需要 +psycopg 后缀，去掉以免方言识别问题
    eng = create_engine(url.replace("+psycopg", ""))
    errors: list[str] = []

    with eng.begin() as conn:
        # 1) UQ: stocks(item_id, location_id)
        uniques = conn.execute(text("""
            SELECT pg_get_constraintdef(c.oid) AS def
            FROM pg_constraint c
            WHERE c.conrelid = 'public.stocks'::regclass
              AND c.contype = 'u'
        """)).fetchall()
        defs_uq = [row[0] for row in uniques]  # 列名叫 def，不能写 row.def
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
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_class r ON r.oid = c.confrelid
            WHERE c.contype = 'f'
              AND t.relname = 'stock_ledger'
              AND r.relname = 'stocks'
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
