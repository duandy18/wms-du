import os
from typing import Any, Optional, Tuple

import psycopg2


def test_psycopg2_connect_smoke() -> None:
    """
    Connect to Postgres only if a valid DATABASE_URL is provided.
    This is a smoke test for local/dev; CI may skip if not configured.
    """
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        # Not a Postgres URL; skip the smoke test gracefully
        return

    # 1) Load connection from env and connect
    conn = psycopg2.connect(db_url)
    try:
        # 2) Create cursor and run a trivial query
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version: Optional[Tuple[Any, ...]] = cur.fetchone()

        # 3) Assert we got a result; print first token if present
        assert version is not None
        first = (
            version[0] if isinstance(version, tuple) and len(version) > 0 else "unknown"
        )
        print("OK Success: connected to database, version:", first)

    finally:
        # 4) Cleanup
        conn.close()
