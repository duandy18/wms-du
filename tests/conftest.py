# tests/conftest.py
# ruff: noqa: E402
from __future__ import annotations

import contextlib
import os
import pathlib
import sys
from collections.abc import Generator, Iterator
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# ---------- bootstrap: set paths & env BEFORE importing app ----------
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("SEED_PROFILE", "minimal")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_unit.db")

# ---------- import app code ----------
from app import db as app_db  # contains get_db & SessionLocal
from app.models import Base
from apps.api import main  # your FastAPI app module

# Prefer the same URL as env, but build our own testing engine
DB_URL = os.environ["DATABASE_URL"]
IS_SQLITE = DB_URL.startswith("sqlite")

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    pool_pre_ping=True,
    future=True,
)


# ---------- helpers ----------
def _sqlite_file_from_url(url: str) -> pathlib.Path | None:
    if not url.startswith("sqlite:///"):
        return None
    # sqlite:///./test_unit.db → path: /./test_unit.db
    p = urlparse(url).path
    return (ROOT / pathlib.Path(p.lstrip("/"))).resolve()


# ---------- schema & seeds at session start ----------
@pytest.fixture(scope="session", autouse=True)
def _prepare_schema_and_seed() -> Iterator[None]:
    """
    Prefer Alembic migrations; fall back to metadata.create_all for early bootstrap.
    Then load minimal seeds if app.seed.load_seed exists.
    """
    # Try Alembic upgrade head (best-effort)
    with contextlib.suppress(Exception):
        import subprocess

        subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=str(ROOT))

    # Fallback: ensure tables exist for any engine
    with contextlib.suppress(Exception):
        Base.metadata.create_all(bind=engine)

    # Optional seed loading (strict mode controlled by SEED_STRICT=1)
    strict_seed = os.environ.get("SEED_STRICT", "0") == "1"
    try:
        from app.seed import load_seed

        seeds_dir = ROOT / "seeds"
        load_seed(db_url=DB_URL, profile=os.environ["SEED_PROFILE"], base_path=seeds_dir)
    except Exception as exc:
        if strict_seed:
            raise
        print(f"[seed] skipped or failed (non-strict): {exc}")

    yield

    # Teardown: clean up sqlite db file
    if IS_SQLITE:
        with contextlib.suppress(Exception):
            f = _sqlite_file_from_url(DB_URL)
            if f and f.exists():
                f.unlink()


# ---------- per-test transactional session ----------
@pytest.fixture()
def db() -> Generator:
    """
    Start a SAVEPOINT transaction per test and roll it back afterwards.
    Avoids inter-test interference without recreating schema.
    """
    connection = engine.connect()
    trans = connection.begin()  # outer transaction
    # Bind a session to the connection so all ORM ops share the same tx
    Session = sessionmaker(bind=connection, autocommit=False, autoflush=False, future=True)
    session = Session()

    # Ensure nested transactions (savepoints) work with SQLAlchemy events
    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        # Re-open a SAVEPOINT for subtransactions if needed
        if trans.nested and not getattr(trans._parent, "nested", False):
            sess.begin_nested()

    try:
        # Start first SAVEPOINT so that flushes are isolated
        session.begin_nested()
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


# ---------- FastAPI client with dependency override ----------
@pytest.fixture()
def client(db) -> Generator:
    def _override_get_db():
        yield db

    main.app.dependency_overrides[app_db.get_db] = _override_get_db
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()
