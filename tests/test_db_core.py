import os

import pytest
from dotenv import load_dotenv

# Skip the whole module on SQLite-only CI (default DATABASE_URL=sqlite:///test.db)
if os.getenv("DATABASE_URL", "").startswith("sqlite"):
    pytest.skip("skip db_core tests on SQLite CI", allow_module_level=True)

# Optional dependency: import psycopg2 only if available (otherwise mark as skipped)
psycopg2 = pytest.importorskip("psycopg2")


# ------------------------- configuration & connection -------------------------

def load_db_config() -> dict:
    """Load DB config from environment/.env (no hard-coded secrets)."""
    load_dotenv()
    return {
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASS"),
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
    }


def open_connection(cfg: dict):
    """Open a PostgreSQL connection using psycopg2."""
    return psycopg2.connect(
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=cfg["port"],
    )


# --------------------------------- fixtures ----------------------------------

@pytest.fixture(scope="module")
def db_connection():
    """
    Provide a DB connection for this module.
    Always closes the connection even if a test fails.
    """
    cfg = load_db_config()
    try:
        conn = open_connection(cfg)
    except psycopg2.OperationalError as e:  # specific, actionable failure
        pytest.fail(f"failed to connect to database: {e}")
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------- tests ------------------------------------

def test_db_connection_version(db_connection):
    """Can execute a trivial query and return a version string."""
    with db_connection.cursor() as cur:
        cur.execute("SELECT version();")
        row = cur.fetchone()

    assert row is not None and isinstance(row[0], str)
    # Example extra assertion: make sure 'PostgreSQL' appears in version string
    assert "PostgreSQL" in row[0]
