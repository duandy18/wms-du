# scripts/sql/schema_snapshot.py
"""
A.sql: schema from Alembic migrations (replayed on a fresh DB)
B.sql: schema from SQLAlchemy metadata.create_all()
Notes:
- Use a temporary SQLite DB for structural diff; do not touch real databases.
- Goal: detect missing tables/columns/constraints; minor dialect differences are OK.
"""

import os
from contextlib import closing

# ORM metadata entry (adjust to your project)
from typing import cast

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine


def get_orm_metadata() -> MetaData:
    try:
        from app.models import metadata as md  # centralized metadata

        return cast(MetaData, md)
    except Exception:
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()
        return cast(MetaData, Base.metadata)


orm_metadata: MetaData = get_orm_metadata()


def dump_sqlite_schema(engine: Engine, outfile: str) -> None:
    with closing(engine.raw_connection()) as conn, open(outfile, "w", encoding="utf-8") as f:
        for raw in conn.iterdump():
            text = str(raw).strip()
            if not text:
                continue
            f.write(text + "\n")


# Prepare temporary SQLite databases
a_engine = create_engine("sqlite:///a_tmp.db")
b_engine = create_engine("sqlite:///b_tmp.db")

# Point Alembic to the temporary SQLite database via env var.
# Ensure alembic.ini has:
# sqlalchemy.url = ${ALEMBIC_SQLITE_URL:${DATABASE_URL:}}
os.environ["ALEMBIC_SQLITE_URL"] = f"sqlite:///{os.path.abspath('a_tmp.db')}"

# Clean leftovers
for path in ("a_tmp.db", "b_tmp.db", "A.sql", "B.sql"):
    if os.path.exists(path):
        os.remove(path)

# 1) Replay migrations into A
ret = os.system("alembic upgrade head")
if ret != 0:
    raise SystemExit("alembic upgrade failed; check migrations.")

dump_sqlite_schema(a_engine, "A.sql")

# 2) Build schema from ORM metadata into B
orm_metadata.create_all(b_engine)
dump_sqlite_schema(b_engine, "B.sql")

print("Generated A.sql (from migrations) and B.sql (from ORM metadata).")
