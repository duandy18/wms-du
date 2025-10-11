#!/usr/bin/env bash
# .github/ci/run.sh
# 目标：把 CI 行为都放在脚本里，workflow 只负责调用本脚本。
# - 在 GitHub Actions 上，为 sqlite 路径剥掉 PG 专属的 server_settings（兜底）。
# - 可选执行 Alembic 迁移（存在 alembic.ini 和 alembic/versions 时）。
# - 统一跑 pytest（可以用环境变量覆盖参数）。

set -Eeuo pipefail

# ---------------------------
# 0) 基础信息与环境检查
# ---------------------------
echo "== Python & Pip =="
python -V
pip --version
echo

echo "== Key env =="
echo "GITHUB_ACTIONS=${GITHUB_ACTIONS:-}"
echo "DATABASE_URL=${DATABASE_URL:-<unset>}"
echo "PYTEST_ARGS=${PYTEST_ARGS:-<default>}"
echo

# 若 CI 环境未显式设置 DATABASE_URL，则强制走 PG
if [[ "${GITHUB_ACTIONS:-}" == "true" && -z "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="postgresql+psycopg://wms:wms@localhost:5432/wms"
  echo "DATABASE_URL not set in CI, defaulting to: $DATABASE_URL"
fi

# ---------------------------------------------
# 1) CI 兜底补丁：剥掉 sqlite 上的 server_settings
#    （真正的早期注入在 sitecustomize.py；此处为双保险）
# ---------------------------------------------
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
python - <<'PY'
import sqlalchemy
from sqlalchemy.engine import make_url

_real = sqlalchemy.create_engine

def _safe(url, *a, **kw):
    try:
        backend = make_url(url).get_backend_name()
    except Exception:
        backend = ""
    if backend.startswith("sqlite"):
        ca = kw.get("connect_args")
        if isinstance(ca, dict) and "server_settings" in ca:
            ca = dict(ca)
            ca.pop("server_settings", None)
            kw["connect_args"] = ca
    return _real(url, *a, **kw)

sqlalchemy.create_engine = _safe  # type: ignore[attr-defined]
print("[ci/run.sh] sqlite server_settings guard active.")
PY
fi

# ---------------------------------------------
# 2) 可选：执行 Alembic 迁移（存在配置时）
# ---------------------------------------------
if [[ -f "alembic.ini" && -d "alembic/versions" ]]; then
  echo "== Alembic upgrade head =="
  alembic upgrade head || {
    echo "!! Alembic failed (non-fatal in CI smoke)."
  }
  echo
else
  echo "== Alembic skipped (alembic.ini or versions missing) =="
fi

# ---------------------------------------------
# 3) 运行测试（允许通过 PYTEST_ARGS 覆盖）
# ---------------------------------------------
echo "== Pytest =="
: "${PYTEST_ARGS:=-q --maxfail=1 --disable-warnings}"
echo "pytest ${PYTEST_ARGS}"
pytest ${PYTEST_ARGS}
