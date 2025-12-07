# sitecustomize.py
import os

USE_GUARD = (os.getenv("GITHUB_ACTIONS", "").lower() == "true") or (
    os.getenv("WMS_SQLITE_GUARD", "") == "1"
)

if USE_GUARD:
    try:
        import sqlalchemy
        from sqlalchemy.engine import make_url, URL
        from sqlalchemy.ext import asyncio as sqla_async

        _real_sync = sqlalchemy.create_engine
        _real_async = sqla_async.create_async_engine

        def _strip(url, *a, **kw):
            """
            只对 sqlite 连接做兼容处理：
            - 去掉 connect_args.server_settings，防止 aiosqlite / sqlite 报错
            - 对 Postgres / 其他后端完全不动，避免 URL 被错误解析
            """
            backend = None
            try:
                # URL 实例：直接拿 backend_name
                if isinstance(url, URL):
                    backend = url.get_backend_name()
                # 字符串：只在看起来像 sqlite 的时候才用 make_url 解析
                elif isinstance(url, str) and url.startswith(("sqlite://", "sqlite+")):
                    backend = make_url(url).get_backend_name()
            except Exception:
                # 解析失败就当没看见，直接放行
                backend = None

            if backend and backend.startswith("sqlite"):
                ca = kw.get("connect_args")
                if isinstance(ca, dict) and "server_settings" in ca:
                    ca = dict(ca)
                    ca.pop("server_settings", None)
                    kw["connect_args"] = ca

            # 非 sqlite：什么都不改
            return a, kw

        def _safe_sync(url, *a, **kw):
            a, kw = _strip(url, *a, **kw)
            return _real_sync(url, *a, **kw)

        def _safe_async(url, *a, **kw):
            a, kw = _strip(url, *a, **kw)
            return _real_async(url, *a, **kw)

        sqlalchemy.create_engine = _safe_sync
        sqla_async.create_async_engine = _safe_async
        print("[sitecustomize] SQLite server_settings guard active (sync+async).")
    except Exception as e:
        print(f"[sitecustomize] Patch failed: {e}")
# 提示你是否开了环境变量
elif os.getenv("WMS_SQLITE_GUARD", "") != "1":
    print("[sitecustomize] Guard inactive (set WMS_SQLITE_GUARD=1 to enable locally)")
