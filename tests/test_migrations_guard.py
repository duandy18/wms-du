import contextlib
import os
import subprocess
from typing import Optional

import pytest

# ---------- Base paths ----------
# Find the nearest alembic.ini inside the repo.
# Priority: repo root -> first-level subdir -> recursive search.


def find_alembic_ini(start_path: str) -> Optional[str]:
    """Search for alembic.ini starting from start_path."""
    candidates = [
        os.path.join(start_path, "alembic.ini"),
        os.path.join(start_path, "app", "alembic.ini"),
        os.path.join(start_path, "apps", "alembic.ini"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    for root, _dirs, files in os.walk(start_path):
        if "alembic.ini" in files:
            return os.path.join(root, "alembic.ini")
    return None


# ---------- Alembic migration guard ----------
def run_alembic_upgrade(db_url: str) -> subprocess.CompletedProcess:
    """Run alembic upgrade head with a given DATABASE_URL."""
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    return subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


# ---------- Tests ----------
def test_alembic_ini_exists():
    """Ensure alembic.ini is discoverable in repo."""
    root = os.getcwd()
    ini_path = find_alembic_ini(root)
    assert ini_path is not None, "alembic.ini not found"


@pytest.mark.parametrize("db_url", ["sqlite:///test_unit.db"])
def test_migrations_apply_cleanly(db_url: str):
    """Ensure alembic migrations can be applied without errors."""
    result = run_alembic_upgrade(db_url)
    assert result.returncode == 0, f"Migration failed: {result.stderr}"


def test_contextlib_usage_demo():
    """Dummy test using contextlib just to silence import warnings."""
    with contextlib.suppress(Exception):
        pass
