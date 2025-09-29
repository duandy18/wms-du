import os
from typing import Any, Optional, Tuple

import pytest


def test_psycopg2_connect_smoke() -> None:
    """
    Connect to Postgres only if a valid DATABASE_URL is provided.
    This is a smoke test for local/dev; CI may skip if not configured.
    """
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        pytest.skip("Not a Postgres URL; skipping psycopg2 smoke test")

    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not installed in this environment")

    # 1) Connect
    conn = psycopg2.connect(db_url)
    try:
        # 2) Run trivial query
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version: Optional[Tuple[Any, ...]] = cur.fetchone()

        # 3) Assert we got a result
        assert version is not None
        first = (
            version[0] if isinstance(version, tuple) and len(version) > 0 else "unknown"
        )
        print("OK Success: connected to database, version:", first)
    finally:
        conn.close()
