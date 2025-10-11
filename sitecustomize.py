"""
CI 兜底补丁：
- 仅在 GitHub Actions 环境生效；
- 全局替换 sqlalchemy.create_engine：
  若目标是 sqlite/aiosqlite，则从 connect_args 中剥掉 server_settings。
"""

import os
if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
    import sqlalchemy  # type: ignore
    from sqlalchemy.engine import make_url  # type: ignore

    _real_create_engine = sqlalchemy.create_engine

    def _safe_create_engine(url, *args, **kwargs):  # noqa: ANN001, D401
        try:
            backend = make_url(url).get_backend_name()
        except Exception:
            backend = ""
        if backend.startswith("sqlite"):
            ca = kwargs.get("connect_args")
            if isinstance(ca, dict) and "server_settings" in ca:
                ca = dict(ca)
                ca.pop("server_settings", None)
                kwargs["connect_args"] = ca
        return _real_create_engine(url, *args, **kwargs)

    sqlalchemy.create_engine = _safe_create_engine  # type: ignore[attr-defined]
