# scripts/sql/schema_snapshot.py
"""
A.sql: schema from Alembic migrations (replayed on a fresh SQLite DB)
B.sql: schema from SQLAlchemy metadata.create_all()
Notes:
- Uses a temporary SQLite workspace; does not touch real databases.
- Goal: detect missing tables/columns/constraints; minor dialect diffs are OK.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import closing, suppress
from pathlib import Path

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base

# project root (scripts/sql/ -> project root)
ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".schema_snapshot_tmp"
WORK.mkdir(exist_ok=True)


# --- 修正了导入路径，从 app.db 导入 Base，metadata 是 Base 的属性 ---
try:
    from app.db import Base as ORM_BASE
except ImportError:
    ORM_BASE = None


def get_orm_metadata() -> MetaData:
    """Return ORM MetaData. Prefer ORM_BASE.metadata; otherwise a dummy Base().metadata."""
    # --- 修正了这里，直接使用 ORM_BASE.metadata ---
    if isinstance(ORM_BASE, declarative_base()):
        return ORM_BASE.metadata

    Base = declarative_base()
    return Base.metadata


def dump_sqlite_schema(engine: Engine, outfile: Path) -> None:
    with (
        closing(engine.raw_connection()) as conn,
        outfile.open("w", encoding="utf-8") as f,
    ):
        for raw in conn.iterdump():
            text = str(raw).strip()
            if text:
                f.write(text + "\n")


def main() -> None:
    a_db = WORK / "a_tmp.db"
    b_db = WORK / "b_tmp.db"
    a_sql = WORK / "A.sql"
    b_sql = WORK / "B.sql"

    # clean leftovers
    for p in (a_db, b_db, a_sql, b_sql):
        with suppress(Exception):
            p.unlink()

    a_engine = create_engine(f"sqlite:///{a_db}")
    b_engine = create_engine(f"sqlite:///{b_db}")

    # point Alembic to temp SQLite db via env var
    # ensure alembic.ini has: sqlalchemy.url = ${ALEMBIC_SQLITE_URL:${DATABASE_URL:}}
    os.environ["ALEMBIC_SQLITE_URL"] = f"sqlite:///{a_db}"

    # 1) migrations -> A.sql
    env = {**os.environ, "PYTHONPATH": str(ROOT)}  # let alembic import app.*
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=str(ROOT), env=env)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"alembic upgrade failed: {exc}") from exc
    dump_sqlite_schema(a_engine, a_sql)

    # 2) ORM metadata -> B.sql
    orm_metadata = get_orm_metadata()
    orm_metadata.create_all(b_engine)
    dump_sqlite_schema(b_engine, b_sql)

    print(f"Generated {a_sql.name} (from migrations) and {b_sql.name} (from ORM metadata).")


if __name__ == "__main__":
    main()
