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

# top-level imports to avoid PLC0415
import subprocess
from typing import Any, Callable

# Try import into a temp name to avoid redefinition issues with mypy
try:
    from app.seed import load_seed as _load_seed  # type: ignore[import-not-found]
except Exception:
    _load_seed = None  # type: ignore[assignment]

# Public name with a precise type: a callable that returns None
load_seed: Callable[..., None]

if _load_seed is None:

    def load_seed(*_a: Any, **_kw: Any) -> None:
        """No-op seed loader for tests; replace with real seeding later."""
        return None

else:
    # If import succeeded, use it
    load_seed = _load_seed


# ---------- import app code ----------
import main  # FastAPI app module
from app import db as app_db  # contains get_db & SessionLocal
from app.models import Base

# ---------- engine & session factory ----------
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
    # sqlite:///./test_unit.db -> path: /./test_unit.db
    p = urlparse(url).path
    return (ROOT / pathlib.Path(p.lstrip("/"))).resolve()


# ---------- schema & seeds at session start ----------
@pytest.fixture(scope="session", autouse=True)
def _prepare_schema_and_seed() -> Iterator[None]:
    """
    Session-level prepare: try Alembic migrations first; fallback to create_all.
    If app.seed.load_seed exists, load seeds according to SEED_PROFILE.
    """
    # migrations (best-effort)
    with contextlib.suppress(Exception):
        subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=str(ROOT))

    # fallback: ensure all tables exist for any engine
    with contextlib.suppress(Exception):
        Base.metadata.create_all(bind=engine)

    # seeds (optional; strict mode via SEED_STRICT=1)
    strict_seed = os.environ.get("SEED_STRICT", "0") == "1"
    if load_seed is not None:
        try:
            seeds_dir = ROOT / "seeds"
            load_seed(
                db_url=DB_URL, profile=os.environ["SEED_PROFILE"], base_path=seeds_dir
            )
        except Exception as exc:
            if strict_seed:
                raise
            print(f"[seed] skipped or failed (non-strict): {exc}")

    yield

    # cleanup sqlite test db file
    if IS_SQLITE:
        with contextlib.suppress(Exception):
            f = _sqlite_file_from_url(DB_URL)
            if f and f.exists():
                f.unlink()


# ---------- per-test transactional session ----------
@pytest.fixture()
def db() -> Generator:
    """
    Each test starts an outer transaction and uses a SAVEPOINT inside.
    It rolls back at the end to isolate tests.
    """
    connection = engine.connect()
    trans = connection.begin()  # outer transaction

    Session = sessionmaker(
        bind=connection, autocommit=False, autoflush=False, future=True
    )
    session = Session()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans_):
        # When an inner transaction ends and parent is not nested, open a new SAVEPOINT
        if trans_.nested and not getattr(trans_._parent, "nested", False):
            sess.begin_nested()

    try:
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

    main.app.dependency_overrides[app_db.get_db] = _override_get_db  # type: ignore[attr-defined]
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()
