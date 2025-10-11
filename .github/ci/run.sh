#!/usr/bin/env bash
set -euo pipefail

# 仅在 GitHub CI 环境下：给 sqlite 兜底，剥掉 server_settings
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
            ca = dict(ca); ca.pop("server_settings", None); kw["connect_args"] = ca
    return _real(url, *a, **kw)
sqlalchemy.create_engine = _safe
PY
fi

# —— 你的 CI 主逻辑（先跑最小 pytest；稳了再加 coverage/ruff/mypy）
pytest -q --maxfail=1 --disable-warnings
