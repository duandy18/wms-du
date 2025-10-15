#!/usr/bin/env python
"""
PostgreSQL schema health check:
- Compare UNIQUE constraints and INDEX definitions against a JSON spec
- Validate column order, uniqueness, and partial index predicate (if any)
- Exit non-zero when mismatches found (for CI)
- Can dump current DB structures as spec baseline (--dump)

Usage:
  python scripts/pg_healthcheck.py --dsn "$DATABASE_URL" --spec scripts/db_spec.json
  python scripts/pg_healthcheck.py --dsn "$DATABASE_URL" --dump > scripts/db_spec.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass

try:
    import psycopg
except ImportError:
    print("Missing dependency: pip install 'psycopg[binary]'", file=sys.stderr)
    raise


# ---------- Data Models ----------
@dataclass
class UniqueSpec:
    name: str
    cols: list[str]


@dataclass
class IndexSpec:
    name: str
    cols: list[str]
    unique: bool = False
    where: str | None = None  # partial index predicate (normalized)


@dataclass
class TableSpec:
    unique: list[UniqueSpec]
    indexes: list[IndexSpec]


Spec = dict[str, TableSpec]  # key: "schema.table"

# ---------- Normalizers ----------
_whitespace_re = re.compile(r"\s+")


def norm_ident(s: str) -> str:
    return s.strip()


def norm_pred(s: str | None) -> str | None:
    if not s:
        return None
    # Compact whitespace and lowercase for stable compare (safe for simple predicates)
    t = _whitespace_re.sub(" ", s).strip()
    return t.lower()


# ---------- Introspection SQL ----------
SQL_UNIQUES = """
SELECT
  ns.nspname AS schema,
  tbl.relname AS "table",
  con.conname AS name,
  array_agg(att.attname ORDER BY ord.pos) AS cols
FROM pg_constraint con
JOIN pg_class tbl ON tbl.oid = con.conrelid
JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
JOIN unnest(con.conkey) WITH ORDINALITY ord(attnum, pos) ON TRUE
JOIN pg_attribute att ON att.attrelid = tbl.oid AND att.attnum = ord.attnum
WHERE con.contype = 'u'
AND ns.nspname NOT IN ('pg_catalog','information_schema')
GROUP BY 1,2,3
ORDER BY 1,2,3;
"""

SQL_INDEXES = """
WITH idx AS (
  SELECT
    ns.nspname AS schema,
    tbl.relname AS "table",
    i.relname  AS name,
    ix.indisunique AS unique,
    pg_get_expr(ix.indpred, ix.indrelid) AS where_pred,
    ix.indkey AS indkey,
    tbl.oid AS toid
  FROM pg_index ix
  JOIN pg_class i   ON i.oid   = ix.indexrelid
  JOIN pg_class tbl ON tbl.oid = ix.indrelid
  JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
  WHERE ns.nspname NOT IN ('pg_catalog','information_schema')
)
SELECT
  idx.schema, idx."table", idx.name, idx.unique,
  idx.where_pred,
  array_agg(att.attname ORDER BY ord.pos) AS cols
FROM idx
JOIN LATERAL unnest(idx.indkey) WITH ORDINALITY ord(attnum, pos) ON TRUE
LEFT JOIN pg_attribute att ON att.attrelid = idx.toid AND att.attnum = ord.attnum
GROUP BY 1,2,3,4,5
ORDER BY 1,2,3;
"""


# ---------- Load/Build Spec ----------
def fetch_uniques(conn) -> list[tuple[str, str, str, list[str]]]:
    rows = conn.execute(SQL_UNIQUES).fetchall()
    return [(r[0], r[1], r[2], [norm_ident(c) for c in r[3]]) for r in rows]


def fetch_indexes(conn) -> list[tuple[str, str, str, bool, str | None, list[str]]]:
    rows = conn.execute(SQL_INDEXES).fetchall()
    out = []
    for schema, table, name, unique, where_pred, cols in rows:
        out.append(
            (
                schema,
                table,
                name,
                bool(unique),
                norm_pred(where_pred),
                [norm_ident(c) for c in cols if c],
            )
        )
    return out


def build_spec_from_db(conn) -> Spec:
    spec: Spec = {}
    # uniques
    for schema, table, name, cols in fetch_uniques(conn):
        key = f"{schema}.{table}"
        spec.setdefault(key, TableSpec(unique=[], indexes=[]))
        spec[key].unique.append(UniqueSpec(name=name, cols=cols))
    # indexes
    for schema, table, name, unique, where_pred, cols in fetch_indexes(conn):
        key = f"{schema}.{table}"
        spec.setdefault(key, TableSpec(unique=[], indexes=[]))
        spec[key].indexes.append(IndexSpec(name=name, cols=cols, unique=unique, where=where_pred))
    # sort for stability
    for t in spec.values():
        t.unique.sort(key=lambda u: (u.name, u.cols))
        t.indexes.sort(key=lambda i: (i.name, i.cols, i.unique, i.where or ""))
    return spec


def load_spec(path: str) -> Spec:
    raw = json.load(open(path, encoding="utf-8"))
    spec: Spec = {}
    for key, val in raw.items():
        us = [
            UniqueSpec(name=x["name"], cols=[norm_ident(c) for c in x["cols"]])
            for x in val.get("unique", [])
        ]
        ix = [
            IndexSpec(
                name=x["name"],
                cols=[norm_ident(c) for c in x["cols"]],
                unique=bool(x.get("unique", False)),
                where=norm_pred(x.get("where")),
            )
            for x in val.get("indexes", [])
        ]
        spec[key] = TableSpec(unique=us, indexes=ix)
    return spec


# ---------- Compare ----------
def as_map_uni(t: TableSpec) -> dict[str, UniqueSpec]:
    return {u.name: u for u in t.unique}


def as_map_idx(t: TableSpec) -> dict[str, IndexSpec]:
    return {i.name: i for i in t.indexes}


def compare(spec: Spec, actual: Spec, strict: bool = False) -> dict:
    failures = []

    # Check that every table in spec exists (best-effort: we only warn if missing)
    for key in spec.keys():
        if key not in actual:
            failures.append({"table": key, "kind": "table_missing", "detail": "table not found"})
            continue

        # Uniques
        exp_uni = as_map_uni(spec[key])
        act_uni = as_map_uni(actual.get(key, TableSpec([], [])))
        for name, eu in exp_uni.items():
            au = act_uni.get(name)
            if not au:
                failures.append({"table": key, "kind": "unique_missing", "name": name})
                continue
            if eu.cols != au.cols:
                failures.append(
                    {
                        "table": key,
                        "kind": "unique_cols_mismatch",
                        "name": name,
                        "expect": eu.cols,
                        "actual": au.cols,
                    }
                )

        # Indexes
        exp_idx = as_map_idx(spec[key])
        act_idx = as_map_idx(actual.get(key, TableSpec([], [])))
        for name, ei in exp_idx.items():
            ai = act_idx.get(name)
            if not ai:
                failures.append({"table": key, "kind": "index_missing", "name": name})
                continue
            if ei.cols != ai.cols:
                failures.append(
                    {
                        "table": key,
                        "kind": "index_cols_mismatch",
                        "name": name,
                        "expect": ei.cols,
                        "actual": ai.cols,
                    }
                )
            if bool(ei.unique) != bool(ai.unique):
                failures.append(
                    {
                        "table": key,
                        "kind": "index_uniqueness_mismatch",
                        "name": name,
                        "expect": ei.unique,
                        "actual": ai.unique,
                    }
                )
            if norm_pred(ei.where) != norm_pred(ai.where):
                failures.append(
                    {
                        "table": key,
                        "kind": "index_predicate_mismatch",
                        "name": name,
                        "expect": ei.where,
                        "actual": ai.where,
                    }
                )

        # In non-strict mode, we ignore extra indexes/uniques in DB.
        if strict:
            # Extra uniques
            for name in set(act_uni.keys()) - set(exp_uni.keys()):
                failures.append({"table": key, "kind": "unique_extra", "name": name})
            # Extra indexes
            for name in set(act_idx.keys()) - set(exp_idx.keys()):
                failures.append({"table": key, "kind": "index_extra", "name": name})

    report = {"failures": failures, "fail_count": len(failures)}
    return report


# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dsn", default=None, help="PostgreSQL DSN; falls back to env DATABASE_URL if omitted"
    )
    ap.add_argument("--spec", default=None, help="Path to JSON spec (omit when using --dump)")
    ap.add_argument("--strict", action="store_true", help="Require no extra indexes/uniques in DB")
    ap.add_argument("--dump", action="store_true", help="Dump current DB as spec JSON and exit")
    args = ap.parse_args()

    dsn = args.dsn or None
    if dsn is None:
        import os

        dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("ERROR: DSN not provided; use --dsn or set DATABASE_URL", file=sys.stderr)
        sys.exit(2)

    with psycopg.connect(dsn) as conn:
        actual = build_spec_from_db(conn)

    if args.dump:
        # Emit compact, stable JSON
        out = {}
        for key, t in actual.items():
            out[key] = {
                "unique": [asdict(u) for u in t.unique],
                "indexes": [asdict(i) for i in t.indexes],
            }
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
        return

    if not args.spec:
        print("ERROR: --spec is required when not using --dump", file=sys.stderr)
        sys.exit(2)

    spec = load_spec(args.spec)
    report = compare(spec, actual, strict=args.strict)

    # Pretty summary + JSON for machines
    if report["fail_count"]:
        print("[PG Healthcheck] ❌ mismatches:", report["fail_count"])
        for f in report["failures"]:
            where = f.get("table", "?")
            name = f.get("name", "-")
            kind = f["kind"]
            detail = ""
            if "expect" in f or "actual" in f:
                detail = f" (expect={f.get('expect')} actual={f.get('actual')})"
            print(f"  - {where} :: {kind} :: {name}{detail}")
        print("\nJSON report:")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(1)
    else:
        print("[PG Healthcheck] ✅ schema matches spec")
        sys.exit(0)


if __name__ == "__main__":
    main()
