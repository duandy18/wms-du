#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Schema audit dump for core tables.

Usage:
  python3 scripts/audit_schema_dump.py \
    --dsn "postgres://wms:wms@127.0.0.1:5433/wms" \
    --out artifacts/ddl_audit/phase_m5

It will generate:
  - 00_meta.txt
  - 01_dplus/<table>.dplus.txt        (\d+ output)
  - 02_constraints/<table>.txt        (constraints details)
  - 03_indexes/<table>.txt            (index definitions)
  - 04_columns/<table>.txt            (columns list + null/default/type)
  - 05_fk/<table>.txt                 (FK relations)
  - 06_checks/<table>.txt             (CHECK expressions)
  - 99_db_overview.txt                (table list, extensions, enums)
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import List


CORE_TABLES: List[str] = [
    "items",
    "item_uoms",
    "purchase_order_lines",
    "inbound_receipt_lines",
    "internal_outbound_lines",
    "lots",
    "stock_ledger",
    "stocks_lot",
    "stock_snapshots",
]


def run_psql_sql(dsn: str, sql: str) -> str:
    # -X: don't read ~/.psqlrc
    # -v ON_ERROR_STOP=1: fail fast
    # -qAt: quiet, unaligned, tuples-only (stable for diff)
    cmd = ["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-qAt", "-c", sql]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"psql failed.\nSQL:\n{sql}\n\nSTDERR:\n{proc.stderr}")
    return proc.stdout


def run_psql_dplus(dsn: str, table: str) -> str:
    # \d+ needs aligned output; don't use -A/-t.
    cmd = ["psql", dsn, "-X", "-v", "ON_ERROR_STOP=1", "-c", rf"\d+ {table}"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"psql \\d+ failed for {table}.\nSTDERR:\n{proc.stderr}")
    return proc.stdout


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def dump_db_overview(dsn: str, out_dir: Path) -> None:
    overview_sql = r"""
-- public schema objects
SELECT c.relkind, c.relname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r','p','v','m')
ORDER BY c.relkind, c.relname;

-- extensions
SELECT extname, extversion FROM pg_extension ORDER BY extname;

-- enum types
SELECT
  t.typname AS enum_name,
  e.enumlabel AS enum_value,
  e.enumsortorder
FROM pg_type t
JOIN pg_enum e ON e.enumtypid = t.oid
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname = 'public'
ORDER BY t.typname, e.enumsortorder;
""".strip()
    write_text(out_dir / "99_db_overview.txt", run_psql_sql(dsn, overview_sql) + "\n")


def dump_table(dsn: str, out_dir: Path, table: str) -> None:
    # 01: \d+
    write_text(out_dir / "01_dplus" / f"{table}.dplus.txt", run_psql_dplus(dsn, table))

    # 04: columns
    columns_sql = f"""
SELECT
  c.ordinal_position,
  c.column_name,
  c.data_type,
  c.udt_name,
  c.is_nullable,
  COALESCE(c.column_default, '')
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.table_name = '{table}'
ORDER BY c.ordinal_position;
""".strip()
    write_text(out_dir / "04_columns" / f"{table}.txt", run_psql_sql(dsn, columns_sql) + "\n")

    # 02: constraints
    constraints_sql = f"""
SELECT
  con.conname AS constraint_name,
  con.contype AS constraint_type,
  pg_get_constraintdef(con.oid, true) AS constraint_def
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
WHERE nsp.nspname = 'public'
  AND rel.relname = '{table}'
ORDER BY con.contype, con.conname;
""".strip()
    write_text(out_dir / "02_constraints" / f"{table}.txt", run_psql_sql(dsn, constraints_sql) + "\n")

    # 03: indexes
    indexes_sql = f"""
SELECT
  idx.relname AS index_name,
  pg_get_indexdef(i.indexrelid) AS index_def
FROM pg_index i
JOIN pg_class tbl ON tbl.oid = i.indrelid
JOIN pg_namespace nsp ON nsp.oid = tbl.relnamespace
JOIN pg_class idx ON idx.oid = i.indexrelid
WHERE nsp.nspname = 'public'
  AND tbl.relname = '{table}'
ORDER BY idx.relname;
""".strip()
    write_text(out_dir / "03_indexes" / f"{table}.txt", run_psql_sql(dsn, indexes_sql) + "\n")

    # 05: FK
    fk_sql = f"""
SELECT
  con.conname AS fk_name,
  pg_get_constraintdef(con.oid, true) AS fk_def
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
WHERE nsp.nspname = 'public'
  AND rel.relname = '{table}'
  AND con.contype = 'f'
ORDER BY con.conname;
""".strip()
    write_text(out_dir / "05_fk" / f"{table}.txt", run_psql_sql(dsn, fk_sql) + "\n")

    # 06: CHECK
    check_sql = f"""
SELECT
  con.conname AS check_name,
  pg_get_constraintdef(con.oid, true) AS check_def
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
WHERE nsp.nspname = 'public'
  AND rel.relname = '{table}'
  AND con.contype = 'c'
ORDER BY con.conname;
""".strip()
    write_text(out_dir / "06_checks" / f"{table}.txt", run_psql_sql(dsn, check_sql) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True, help='e.g. "postgres://wms:wms@127.0.0.1:5433/wms"')
    ap.add_argument("--out", required=True, help="output directory, e.g. artifacts/ddl_audit/phase_m5")
    ap.add_argument("--tables", default=",".join(CORE_TABLES), help="comma-separated table list")
    args = ap.parse_args()

    dsn = args.dsn
    out_dir = Path(args.out).resolve()
    tables = [t.strip() for t in args.tables.split(",") if t.strip()]

    out_dir.mkdir(parents=True, exist_ok=True)

    write_text(
        out_dir / "00_meta.txt",
        "\n".join(
            [
                "Schema Audit Dump",
                f"DSN: {dsn}",
                "",
                "Fill alembic outputs here (optional):",
                "  - alembic history",
                "  - alembic current",
                "  - alembic upgrade head",
                "",
            ]
        ),
    )

    dump_db_overview(dsn, out_dir)
    for t in tables:
        dump_table(dsn, out_dir, t)

    print(f"[OK] schema audit dumped to: {out_dir}")


if __name__ == "__main__":
    main()
