# app/db/engine.py
# 统一引擎工厂：PG 下注入 server_settings；SQLite 禁止 server_settings
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

__all__ = ["create_async_engine_safe", "create_sync_engine"]


def _connect_args_for(url_str: str) -> dict[str, Any]:
    """
    返回后端专属 connect_args：
    - PostgreSQL(psycopg): server_settings
    - SQLite: 仅 check_same_thread，绝不带 server_settings
    """
    u = make_url(url_str)
    backend = u.get_backend_name()  # "postgresql", "sqlite", ...

    if backend.startswith("postgresql"):
        return {
            "server_settings": {
                "application_name": "wms-du-ci",
                # "jit": "off",
            }
        }

    if backend.startswith("sqlite"):
        return {"check_same_thread": False}

    return {}


def _maybe_instrument_sqlalchemy(engine) -> None:
    """
    Phase 2.8: 若可用则注入 SQLAlchemy 的 OTel tracing；失败静默。
    这样 main.py 中对 FastAPI 的 tracing 与这里的 DB tracing 可“分处初始化、互不干扰”。
    """
    try:
        # 延迟导入以避免在 early import 时引起循环依赖
        from app.obs.otel import setup_tracing  # type: ignore
        setup_tracing(sqlalchemy_engine=engine)
    except Exception:
        # tracing 失败时不阻断主流程
        pass


def create_sync_engine(url_str: str, *, echo: bool = False):
    connect_args: dict[str, Any] = _connect_args_for(url_str)
    u = make_url(url_str)

    kwargs: dict[str, Any] = {"echo": echo}
    if u.get_backend_name().startswith("postgresql"):
        kwargs["pool_pre_ping"] = True
    if connect_args:
        kwargs["connect_args"] = connect_args

    engine = create_engine(url_str, **kwargs)
    _maybe_instrument_sqlalchemy(engine)  # ← OTel: DB tracing
    return engine


def create_async_engine_safe(url_str: str, *, echo: bool = False) -> AsyncEngine:
    """Async 版（用于 'postgresql+psycopg*' 或 'sqlite+aiosqlite'）。"""
    connect_args: dict[str, Any] = _connect_args_for(url_str)
    u = make_url(url_str)

    kwargs: dict[str, Any] = {"echo": echo}
    if u.get_backend_name().startswith("postgresql"):
        kwargs["pool_pre_ping"] = True
    if connect_args:
        kwargs["connect_args"] = connect_args

    engine = create_async_engine(url_str, **kwargs)
    # AsyncEngine 由 OTel 的 SQLAlchemyInstrumentor 以 engine 实例为粒度注入；
    # 这里同样尝试注入（失败静默），以便链路完整。
    _maybe_instrument_sqlalchemy(engine)
    return engine
