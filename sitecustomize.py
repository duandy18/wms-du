import os

USE_GUARD = (os.getenv("GITHUB_ACTIONS","").lower() == "true") or (os.getenv("WMS_SQLITE_GUARD","") == "1")

if USE_GUARD:
    try:
        import sqlalchemy
        from sqlalchemy.engine import make_url
        from sqlalchemy.ext import asyncio as sqla_async

        _real_sync  = sqlalchemy.create_engine
        _real_async = sqla_async.create_async_engine

        def _strip(url,*a,**kw):
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
            return a, kw

        def _safe_sync(url,*a,**kw):
            a, kw = _strip(url,*a,**kw)
            return _real_sync(url,*a,**kw)

        def _safe_async(url,*a,**kw):
            a, kw = _strip(url,*a,**kw)
            return _real_async(url,*a,**kw)

        sqlalchemy.create_engine       = _safe_sync
        sqla_async.create_async_engine = _safe_async
        print("[sitecustomize] SQLite server_settings guard active (sync+async).")
    except Exception as e:
        print(f"[sitecustomize] Patch failed: {e}")
else:
    # 提示你是否开了环境变量
    if os.getenv("WMS_SQLITE_GUARD","") != "1":
        print("[sitecustomize] Guard inactive (set WMS_SQLITE_GUARD=1 to enable locally)")
