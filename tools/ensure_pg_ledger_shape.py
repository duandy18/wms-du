#!/usr/bin/env python3
"""
ensure_pg_ledger_shape.py — Read-only shape/consistency checks for PostgreSQL.

Guarantees (fail-fast):
1) stock_ledger has required columns with sensible types:
   - stock_id:int, reason:text/varchar, after_qty:numeric, delta:numeric,
     occurred_at:timestamptz, ref:text/varchar, ref_line:int
   - Critical NOT NULL cols have no NULLs: stock_id, reason, after_qty, delta, occurred_at
2) FK consistency: every stock_ledger.stock_id exists in stocks.id
3) No duplicate (reason,ref,ref_line) triplets (when all three NOT NULL)
4) stocks enforces UNIQUE(item_id, location_id) via unique index or constraint
5) Zero side effects. Exit 0 on green; non-zero on failure.

Usage:
  python tools/ensure_pg_ledger_shape.py postgresql+psycopg://wms:wms@127.0.0.1:5433/wms
Options:
  --schema default "public"
  --table  default "stock_ledger"
  --stocks default "stocks"
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass

from sqlalchemy import create_engine, text


def fail(msg: str, code: int = 1) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(code)


@dataclass
class ColSpec:
    name: str
    accept_types: tuple[str, ...]  # substring match against information_schema.data_type


def fetch_cols(conn, schema: str, table: str) -> dict[str, str]:
    rows = conn.execute(
        text(
            """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = :s AND table_name = :t
        """
        ),
        {"s": schema, "t": table},
    ).fetchall()
    return {r.column_name: (r.data_type or "").lower() for r in rows}


def has_unique(conn, schema: str, table: str, cols: Iterable[str]) -> bool:
    """
    Return True if there is an EXACT unique index OR constraint on given cols (in order).
    Checks both pg_index (unique indexes) and pg_constraint (unique constraints).
    """
    want = tuple(cols)

    # 1) unique indexes (column order preserved via WITH ORDINALITY)
    idx_rows = conn.execute(
        text(
            """
        SELECT i.relname AS index_name,
               ix.indisunique AS is_unique,
               array_agg(a.attname ORDER BY k.ord) AS cols
        FROM pg_index ix
        JOIN pg_class t  ON t.oid = ix.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_class i  ON i.oid = ix.indexrelid
        JOIN unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = :s AND t.relname = :t
        GROUP BY i.relname, ix.indisunique
        """
        ),
        {"s": schema, "t": table},
    ).fetchall()
    for r in idx_rows:
        if r.is_unique and tuple(r.cols) == want:
            return True

    # 2) unique constraints (contype='u')
    c_rows = conn.execute(
        text(
            """
        SELECT conname,
               array_agg(a.attname ORDER BY k.ord) AS cols
        FROM pg_constraint c
        JOIN pg_class t  ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = :s AND t.relname = :t AND c.contype = 'u'
        GROUP BY conname
        """
        ),
        {"s": schema, "t": table},
    ).fetchall()
    for r in c_rows:
        if tuple(r.cols) == want:
            return True

    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("database_url", help='e.g. "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"')
    ap.add_argument("--schema", default="public")
    ap.add_argument("--table", default="stock_ledger")
    ap.add_argument("--stocks", default="stocks")
    args = ap.parse_args()

    eng = create_engine(args.database_url)

    with closing(eng.connect()) as conn:
        # 0) table existence
        exists = conn.execute(
            text("SELECT to_regclass(:q) IS NOT NULL"), {"q": f"{args.schema}.{args.table}"}
        ).scalar()
        if not exists:
            fail(f"table {args.schema}.{args.table} does not exist")

        stocks_exist = conn.execute(
            text("SELECT to_regclass(:q) IS NOT NULL"), {"q": f"{args.schema}.{args.stocks}"}
        ).scalar()
        if not stocks_exist:
            fail(f"referenced table {args.schema}.{args.stocks} does not exist")

        # 1) required columns + types
        required = {
            "stock_id": ColSpec("stock_id", ("integer", "bigint")),
            "reason": ColSpec("reason", ("character varying", "text")),
            "after_qty": ColSpec(
                "after_qty", ("numeric", "integer", "bigint", "double precision", "real")
            ),
            "delta": ColSpec("delta", ("numeric", "integer", "bigint", "double precision", "real")),
            "occurred_at": ColSpec("occurred_at", ("timestamp with time zone",)),
            "ref": ColSpec("ref", ("character varying", "text")),
            "ref_line": ColSpec("ref_line", ("integer", "bigint")),
        }

        cols = fetch_cols(conn, args.schema, args.table)
        missing = [k for k in required if k not in cols]
        if missing:
            fail(f"[{args.table}] missing columns: {missing}")

        mismatch = []
        for k, spec in required.items():
            got = cols.get(k, "")
            if not any(t in got for t in spec.accept_types):
                mismatch.append((k, got, spec.accept_types))
        if mismatch:
            lines = [f"{k}: got '{got}', want contains {want}" for k, got, want in mismatch]
            fail(f"[{args.table}] type mismatch:\n  " + "\n  ".join(lines))

        # 2) critical NOT NULLs no NULLs
        criticals = ("stock_id", "reason", "after_qty", "delta", "occurred_at")
        for col in criticals:
            cnt = conn.execute(
                text(f"SELECT COUNT(*) FROM {args.schema}.{args.table} WHERE {col} IS NULL")
            ).scalar()
            if (cnt or 0) > 0:
                fail(f"[{args.table}] column {col} has {cnt} NULL rows")

        # 3) FK consistency
        missing_fk = conn.execute(
            text(
                f"""
            SELECT COUNT(*)
            FROM {args.schema}.{args.table} l
            LEFT JOIN {args.schema}.{args.stocks} s ON s.id = l.stock_id
            WHERE s.id IS NULL
            """
            )
        ).scalar()
        if (missing_fk or 0) > 0:
            print("[DIAG] bad FK rows (stock_id not in stocks.id), up to 20:")
            bad_rows = conn.execute(
                text(
                    f"""
                SELECT l.stock_id, l.reason, l.ref, l.ref_line
                FROM {args.schema}.{args.table} l
                LEFT JOIN {args.schema}.{args.stocks} s ON s.id = l.stock_id
                WHERE s.id IS NULL
                LIMIT 20
                """
                )
            ).fetchall()
            for r in bad_rows:
                print("  -", dict(r._mapping))
            fail(f"[{args.table}] {missing_fk} rows have invalid stock_id")

        # 4) no duplicated (reason,ref,ref_line)
        dup_cnt = conn.execute(
            text(
                f"""
            SELECT COUNT(*) FROM (
              SELECT reason, ref, ref_line, COUNT(*) AS c
              FROM {args.schema}.{args.table}
              WHERE reason IS NOT NULL AND ref IS NOT NULL AND ref_line IS NOT NULL
              GROUP BY reason, ref, ref_line
              HAVING COUNT(*) > 1
            ) t
            """
            )
        ).scalar()
        if (dup_cnt or 0) > 0:
            print("[DIAG] duplicated (reason,ref,ref_line) samples (up to 20):")
            rows = conn.execute(
                text(
                    f"""
                SELECT reason, ref, ref_line, COUNT(*) AS c
                FROM {args.schema}.{args.table}
                WHERE reason IS NOT NULL AND ref IS NOT NULL AND ref_line IS NOT NULL
                GROUP BY reason, ref, ref_line
                HAVING COUNT(*) > 1
                ORDER BY c DESC
                LIMIT 20
                """
                )
            ).fetchall()
            for r in rows:
                print("  -", dict(r._mapping))
            fail(f"[{args.table}] found {dup_cnt} duplicate triplets of (reason,ref,ref_line)")

        # 5) UNIQUE(item_id, location_id) on stocks
        if not has_unique(conn, args.schema, args.stocks, ("item_id", "location_id")):
            fail(f"[{args.stocks}] UNIQUE(item_id, location_id) is missing")

        print("[OK] ledger/stocks shape valid — columns, types, FK, and uniqueness all good.")
        sys.exit(0)


if __name__ == "__main__":
    main()
