#!/usr/bin/env python3
"""
数据库结构不变式（invariants）断言工具：
- 通用：表/列/唯一约束存在性
- PG 专属：触发器存在性；--fix 时幂等重建（来源于 tools/sql/*.sql）
环境变量：
  DATABASE_URL   必填
  WMS_DB_FIX=1   允许执行修复（默认只断言）
  WMS_SQLITE_GUARD 可与仓库既有守卫共存（不影响本脚本）
用法：
  python tools/db_invariants.py --check
  WMS_DB_FIX=1 python tools/db_invariants.py --fix
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from dataclasses import dataclass

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

PG_BACKEND_PREFIX = ("postgresql", "postgresql+psycopg", "postgresql+asyncpg")
SQLITE_PREFIX = ("sqlite",)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


def _get_backend(url: str) -> str:
    low = url.lower()
    for p in PG_BACKEND_PREFIX:
        if low.startswith(p):
            return "pg"
    for p in SQLITE_PREFIX:
        if low.startswith(p):
            return "sqlite"
    return "unknown"


def _read_sql(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ============ 通用不变式：表/列/唯一约束 ============
def assert_core_schema(conn: Connection) -> list[CheckResult]:
    insp = inspect(conn)
    want_tables = {
        "items": ["id"],
        "warehouses": ["id"],
        "locations": ["id", "warehouse_id"],
        "stocks": ["id", "item_id", "location_id", "qty"],
        "stock_ledger": ["id", "stock_id", "delta", "item_id"],
    }
    out: list[CheckResult] = []

    tables = set(insp.get_table_names())
    for t, cols in want_tables.items():
        if t in tables:
            cols_have = {c["name"] for c in insp.get_columns(t)}
            missing = [c for c in cols if c not in cols_have]
            out.append(
                CheckResult(
                    f"table:{t}",
                    ok=(len(missing) == 0),
                    detail=("ok" if not missing else f"missing cols: {missing}"),
                )
            )
        else:
            out.append(CheckResult(f"table:{t}", ok=False, detail="missing table"))

    # stocks 唯一约束 (item_id, location_id)
    try:
        uq_ok = False
        for uq in insp.get_unique_constraints("stocks"):
            if set(uq.get("column_names", []) or []) == {"item_id", "location_id"}:
                uq_ok = True
                break
        out.append(
            CheckResult(
                "constraint:uq_stocks_item_location",
                uq_ok,
                "ok" if uq_ok else "missing",
            )
        )
    except Exception as e:
        out.append(CheckResult("constraint:uq_stocks_item_location", False, f"error: {e}"))

    return out


# ============ PG：触发器存在性 & 重建 ============
def _pg_has_trigger(conn: Connection, table: str, trigger: str) -> bool:
    sql = text(
        """
        SELECT 1
        FROM pg_trigger tg
        JOIN pg_class   tbl ON tg.tgrelid = tbl.oid
        WHERE NOT tg.tgisinternal
          AND tbl.relname = :table
          AND tg.tgname   = :trigger
        LIMIT 1;
    """
    )
    return conn.execute(sql, {"table": table, "trigger": trigger}).first() is not None


def assert_pg_triggers(conn: Connection) -> list[CheckResult]:
    out: list[CheckResult] = []
    want = [
        ("stock_ledger", "trg_stock_ledger_fill_item_id"),
        # 未来：("stock_ledger", "trg_stock_ledger_snapshot_rollup") 等
    ]
    for table, trg in want:
        ok = _pg_has_trigger(conn, table, trg)
        out.append(CheckResult(f"trigger:{table}.{trg}", ok, "ok" if ok else "missing"))
    return out


def _pg_exec_sql_file(conn: Connection, path: str) -> None:
    ddl = _read_sql(path)
    if ddl.strip():
        conn.execute(text(ddl))


def _pg_fix_triggers(conn: Connection, sql_dir: str) -> None:
    # 幂等重建（若无则建，若有则替换）
    _pg_exec_sql_file(conn, os.path.join(sql_dir, "010_triggers_stock_ledger.sql"))
    # 未来快照：当前是占位文件，允许为空
    _pg_exec_sql_file(conn, os.path.join(sql_dir, "020_triggers_snapshots_future.sql"))


# ============ 主流程 ============
def run(check_only: bool, fix: bool, sql_dir: str) -> int:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    backend = _get_backend(url)
    eng = create_engine(url)
    rc = 0
    try:
        with eng.begin() as conn:
            results: list[CheckResult] = []
            results += assert_core_schema(conn)

            if backend == "pg":
                results += assert_pg_triggers(conn)
                if fix:
                    _pg_fix_triggers(conn, sql_dir)
                    # 复查
                    results = assert_core_schema(conn) + assert_pg_triggers(conn)

            # 汇总输出
            has_fail = False
            for r in results:
                status = "OK " if r.ok else "FAIL"
                print(f"[{status}] {r.name} :: {r.detail}")
                if not r.ok:
                    has_fail = True

            if has_fail and not fix:
                rc = 1
    except SQLAlchemyError as e:
        print(f"DB error: {e}", file=sys.stderr)
        rc = 3
    finally:
        eng.dispose()
    return rc


def main():
    parser = argparse.ArgumentParser(
        description="Assert DB schema/constraints and (optionally) self-heal triggers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python tools/db_invariants.py --check
              WMS_DB_FIX=1 python tools/db_invariants.py --fix
        """
        ),
    )
    parser.add_argument("--check", action="store_true", help="only assert, non-zero on mismatch")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="self-heal (create/replace triggers) then re-assert",
    )
    parser.add_argument("--sql-dir", default=os.path.join(os.path.dirname(__file__), "sql"))
    args = parser.parse_args()

    fix = bool(args.fix) or os.getenv("WMS_DB_FIX") == "1"
    check_only = bool(args.check) or not fix
    sys.exit(run(check_only=check_only, fix=fix, sql_dir=args.sql_dir))


if __name__ == "__main__":
    main()
