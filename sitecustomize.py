"""
CI 兜底补丁（仅在 GitHub Actions 环境生效）：
- 同步：替换 sqlalchemy.create_engine，若后端是 sqlite/aiosqlite，则剥掉 connect_args.server_settings；
- 异步：替换 sqlalchemy.ext.asyncio.create_async_engine，同样逻辑；
确保任何路径（包括导入时创建）都不会把 PG 的 server_settings 传给 sqlite。
"""
import os

if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
    try:
        import sqlalchemy
        from sqlalchemy.engine import make_url
        from sqlalchemy.ext import asyncio as sqla_async
    except Exception:
        sqlalchemy = None
        make_url = None
        sqla_async = None

    if sqlalchemy and make_url:
        _real_create_engine = sqlalchemy.create_engine

        def _safe_create_engine(url, *args, **kwargs):
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

        sqlalchemy.create_engine = _safe_create_engine

    if sqla_async and make_url:
        _real_create_async_engine = sqla_async.create_async_engine

        def _safe_create_async_engine(url, *args, **kwargs):
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
            return _real_create_async_engine(url, *args, **kwargs)

        sqla_async.create_async_engine = _safe_create_async_engine
