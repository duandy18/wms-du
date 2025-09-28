# tests/test_db_connection.py
import importlib
import os
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

# 动态加载 app.db, 避免硬编码和 mypy unused ignore
_db = importlib.import_module("app.db")
get_engine: Callable[[], Any] | None = getattr(_db, "get_engine", None)
_engine: Any = getattr(_db, "engine", None)


def _ensure_engine():
    os.environ.setdefault("DATABASE_URL", "sqlite:///./tmp_test.db")
    if get_engine is not None:
        return get_engine()
    assert _engine is not None, "app.db.engine is required when get_engine is missing"
    return _engine


def test_db_connect_smoke(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path/'t.db'}"
    engine = _ensure_engine()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
