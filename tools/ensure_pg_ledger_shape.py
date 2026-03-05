#!/usr/bin/env python3
"""
ensure_pg_ledger_shape.py — Read-only shape/consistency checks for PostgreSQL (Phase 4E lot-world).

Guarantees (fail-fast):
1) stock_ledger has required columns with sensible types:
   - item_id:int, warehouse_id:int, reason:text/varchar,
     delta:numeric/int, occurred_at:timestamptz, ref:text/varchar, ref_line:int
   - after_qty is optional but recommended
2) If stock_ledger.lot_id exists: every non-null lot_id exists in lots.id
3) No duplicate (reason,ref,ref_line) triplets (when all three NOT NULL)
4) stocks_lot has unique constraint uq_stocks_lot_item_wh_lot
5) Zero side effects. Exit 0 on green; non-zero on failure.

Usage:
  python3 tools/ensure_pg_ledger_shape.py postgresql+psycopg://wms:wms@127.0.0.1:5433/wms
Options:
  --schema default "public"
  --ledger default "stock_ledger"
  --lots   default "lots"
  --stocks_lot default "stocks_lot"
"""
from __future__ import annotations

import argparse
import sys
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


def has_unique_constraint(conn, schema: str, table: str, constraint_name: str) -> bool:
    got = conn.execute(
        text(
            """
            SELECT 1
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
             WHERE n.nspname = :s
               AND t.relname = :t
               AND c.contype = 'u'
               AND c.conname = :c
             LIMIT 1
            """
        ),
        {"s": schema, "t": table, "c": constraint_name},
    ).scalar()
    return got == 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("database_url", help='e.g. "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"')
    ap.add_argument("--schema", default="public")
    ap.add_argument("--ledger", default="stock_ledger")
    ap.add_argument("--lots", default="lots")
    ap.add_argument("--stocks_lot", default="stocks_lot")
    args = ap.parse_args()

    eng = create_engine(args.database_url)

    with closing(eng.connect()) as conn:
        def _exists(tbl: str) -> bool:
            return bool(
                conn.execute(
                    text("SELECT to_regclass(:q) IS NOT NULL"),
                    {"q": f"{args.schema}.{tbl}"},
                ).scalar()
            )

        if not _exists(args.ledger):
            fail(f"table {args.schema}.{args.ledger} does not exist")
        if not _exists(args.lots):
            fail(f"table {args.schema}.{args.lots} does not exist")
        if not _exists(args.stocks_lot):
            fail(f"table {args.schema}.{args.stocks_lot} does not exist")

        cols = fetch_cols(conn, args.schema, args.ledger)

        required = {
            "item_id": ColSpec("item_id", ("integer", "bigint")),
            "warehouse_id": ColSpec("warehouse_id", ("integer", "bigint")),
            "reason": ColSpec("reason", ("character varying", "text")),
            "delta": ColSpec("delta", ("numeric", "integer", "bigint", "double precision", "real")),
            "occurred_at": ColSpec("occurred_at", ("timestamp with time zone",)),
            "ref": ColSpec("ref", ("character varying", "text")),
            "ref_line": ColSpec("ref_line", ("integer", "bigint")),
        }

        missing = [k for k in required if k not in cols]
        if missing:
            fail(f"[{args.ledger}] missing columns: {missing}")

        mismatch = []
        for k, spec in required.items():
            got = cols.get(k, "")
            if not any(t in got for t in spec.accept_types):
                mismatch.append((k, got, spec.accept_types))
        if mismatch:
            lines = [f"{k}: got '{got}', want contains {want}" for k, got, want in mismatch]
            fail(f"[{args.ledger}] type mismatch:\n  " + "\n  ".join(lines))

        # If lot_id exists: validate FK
        if "lot_id" in cols:
            bad = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                      FROM {args.schema}.{args.ledger} l
                      LEFT JOIN {args.schema}.{args.lots} lo ON lo.id = l.lot_id
                     WHERE l.lot_id IS NOT NULL AND lo.id IS NULL
                    """
                )
            ).scalar()
            if (bad or 0) > 0:
                fail(f"[{args.ledger}] {bad} rows have invalid lot_id (not in lots.id)")

        # No dup (reason,ref,ref_line)
        dup = conn.execute(
            text(
                f"""
                SELECT COUNT(*) FROM (
                  SELECT reason, ref, ref_line, COUNT(*) AS c
                  FROM {args.schema}.{args.ledger}
                  WHERE reason IS NOT NULL AND ref IS NOT NULL AND ref_line IS NOT NULL
                  GROUP BY reason, ref, ref_line
                  HAVING COUNT(*) > 1
                ) t
                """
            )
        ).scalar()
        if (dup or 0) > 0:
            fail(f"[{args.ledger}] found duplicate (reason,ref,ref_line) triplets: {dup}")

        # stocks_lot unique constraint
        if not has_unique_constraint(conn, args.schema, args.stocks_lot, "uq_stocks_lot_item_wh_lot"):
            fail(f"[{args.stocks_lot}] missing unique constraint uq_stocks_lot_item_wh_lot")

        print("[OK] Phase 4E lot-world shape valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()
