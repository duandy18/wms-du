#!/usr/bin/env bash
set -Eeuo pipefail

echo "== Python & Pip =="; python -V; pip --version; echo
echo "== Key env =="; echo "GITHUB_ACTIONS=${GITHUB_ACTIONS:-}"; echo "DATABASE_URL=${DATABASE_URL:-<unset>}"; echo

# CI 未显式设 DB，则强制走 PG
if [[ "${GITHUB_ACTIONS:-}" == "true" && -z "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="postgresql+psycopg://wms:wms@localhost:5432/wms"  # pragma: allowlist secret
  echo "DATABASE_URL -> $DATABASE_URL"
fi

# 二次保险：同步+异步都剥掉 sqlite 的 server_settings
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
python - <<'PY'
import sqlalchemy
from sqlalchemy.engine import make_url
from sqlalchemy.ext import asyncio as _sqla_async
_real_sync = sqlalchemy.create_engine
def _safe_sync(url,*a,**kw):
    try: backend = make_url(url).get_backend_name()
    except Exception: backend = ""
    if backend.startswith("sqlite"):
        ca = kw.get("connect_args")
        if isinstance(ca, dict) and "server_settings" in ca:
            ca = dict(ca); ca.pop("server_settings", None); kw["connect_args"] = ca
    return _real_sync(url,*a,**kw)
sqlalchemy.create_engine = _safe_sync
_real_async = _sqla_async.create_async_engine
def _safe_async(url,*a,**kw):
    try: backend = make_url(url).get_backend_name()
    except Exception: backend = ""
    if backend.startswith("sqlite"):
        ca = kw.get("connect_args")
        if isinstance(ca, dict) and "server_settings" in ca:
            ca = dict(ca); ca.pop("server_settings", None); kw["connect_args"] = ca
    return _real_async(url,*a,**kw)
_sqla_async.create_async_engine = _safe_async
print("[ci/run.sh] sqlite guard active (sync+async).")
PY
fi

# 可选迁移（失败不致命）
if [[ -f "alembic.ini" && -d "alembic/versions" ]]; then
  echo "== Alembic upgrade head =="; alembic upgrade head || echo "!! Alembic failed (non-fatal)"; echo
else
  echo "== Alembic skipped =="
fi

# ---------------------------------------------
# 3) 运行测试（允许通过 PYTEST_ARGS/PYTEST_K 覆盖）
# ---------------------------------------------
ARGS=()
# 基础参数
if [[ -n "${PYTEST_ARGS:-}" ]]; then
  # 以空格分割追加（例如 -q --maxfail=1 --disable-warnings）
  read -r -a _base <<< "${PYTEST_ARGS}"
  ARGS+=("${_base[@]}")
else
  ARGS+=(-q --maxfail=1 --disable-warnings)
fi
# -k 表达式作为一个参数传入
if [[ -n "${PYTEST_K:-}" ]]; then
  ARGS+=(-k "${PYTEST_K}")
fi
echo "== Pytest =="; echo "pytest ${ARGS[*]}"
pytest "${ARGS[@]}"
