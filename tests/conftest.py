# tests/conftest.py
# ruff: noqa: E402

import contextlib
import os
import pathlib
from collections.abc import Generator

# === Key fix: switch to SQLite test DB before importing any app code ===
ROOT = pathlib.Path(__file__).resolve().parents[1]
os.environ.setdefault("PYTHONPATH", str(ROOT))
os.environ["DATABASE_URL"] = "sqlite:///./test_unit.db"
os.environ["TESTING"] = "1"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as app_db  # must contain get_db (or equivalent) for dependency override
from app.models import Base

# === now import your project code ===
from apps.api import main  # FastAPI instance app; will read SQLite from above env

# independent test database engine (matches env)
engine = create_engine(
    os.environ["DATABASE_URL"],
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_db():
    # reset schema to ensure clean state
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # clean up test db file
    if os.environ["DATABASE_URL"].startswith("sqlite:///./"):
        with contextlib.suppress(Exception):
            os.remove("./test_unit.db")


@pytest.fixture()
def db() -> Generator:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db) -> Generator:
    def _override_get_db():
        yield db

    main.app.dependency_overrides[app_db.get_db] = _override_get_db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
