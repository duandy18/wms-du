#!/usr/bin/env bash
set -euo pipefail

# tiny logger
log() { echo "[$(date +'%H:%M:%S')] $*"; }

# Command selector: test (default) | env | smoke | full
CMD="${1:-test}"

# Default envs (safe for local & CI)
: "${DATABASE_URL:=sqlite:///test.db}"
: "${ENABLE_DIAG:=0}"
: "${JWT_SECRET:=dev-temp-secret}"
: "${PYTHONPATH:=.}"

wait_pg() {
  python - <<'PY'
import os, sys, time, socket, urllib.parse
url = os.environ.get("DATABASE_URL","")
p = urllib.parse.urlparse(url)
if p.scheme.startswith("postgres"):
    host = p.hostname or "localhost"
    port = p.port or 5432
    deadline = time.time()+60
    while time.time() < deadline:
        s = socket.socket()
        try:
            s.settimeout(2); s.connect((host, port)); s.close()
            print("[wait_pg] PostgreSQL is up"); sys.exit(0)
        except Exception:
            time.sleep(1)
    print("[wait_pg] timeout waiting for PostgreSQL", file=sys.stderr)
    sys.exit(1)
else:
    print("[wait_pg] using SQLite; skip wait")
    sys.exit(0)
PY
}

prepare_db() {
  # If alembic exists, upgrade head; tolerate projects without migrations
  if [ -f "alembic.ini" ] || [ -d "app/db/migrations" ] || [ -d "alembic" ]; then
    log "alembic upgrade head"
    alembic upgrade head
  else
    log "no migrations; skip alembic"
  fi
}

run_smoke() {
  # Ultra-fast guardrail; do not collect coverage here
  pytest -q -m "smoke" --maxfail=1 --disable-warnings
}

run_full() {
  # Full test suite with coverage and gates
  pytest -q \
    --maxfail=1 --disable-warnings \
    --cov=app --cov-report=xml:coverage.xml --cov-report=html:htmlcov \
    --junitxml=junit.xml \
    --cov-fail-under=55
}

case "$CMD" in
  env)
    echo "DATABASE_URL=$DATABASE_URL"
    echo "ENABLE_DIAG=$ENABLE_DIAG"
    echo "JWT_SECRET=(set)"
    echo "PYTHONPATH=$PYTHONPATH"
    python -V || true
    pip -V || true
    ;;

  smoke)
    log "Stage A: smoke"
    wait_pg
    prepare_db
    run_smoke
    log "Smoke done"
    ;;

  full)
    log "Stage B: full"
    wait_pg
    prepare_db
    run_full
    log "Full done"
    ;;

  test)
    log "Start CI"
    wait_pg
    prepare_db
    log "Stage A: smoke"
    run_smoke
    log "Stage B: full"
    run_full
    log "Done"
    ;;

  *)
    echo "Usage: $0 {env|smoke|full|test}"
    exit 2
    ;;
esac
