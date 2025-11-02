# app/utils/elog.py
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _elog_url() -> str:
    """
    选择日志写库的 URL：
      1) EVENTLOG_DATABASE_URL（若你想把事件日志分库）
      2) DATABASE_URL_ASYNC（若 Alembic 用 psycopg，同步 URL 在 DATABASE_URL；异步在这个变量）
      3) 回退到常用默认（本地 5433）
    """
    return (
        os.getenv("EVENTLOG_DATABASE_URL")
        or os.getenv("DATABASE_URL_ASYNC")
        or "postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms"
    )


@asynccontextmanager
async def _elog_conn():
    """
    独立异步 Engine + 连接，用完即销毁。
    与业务事务解耦，保证日志写入不会影响/被影响。
    """
    engine = create_async_engine(_elog_url(), future=True, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            yield conn
    finally:
        await engine.dispose()


def _json_default(o: Any) -> str:
    """
    解决 json.dumps 无法序列化 date/datetime 的问题。
    统一转 ISO 字符串。
    """
    if isinstance(o, (datetime, date)):
        # 统一 ISO 格式，datetime 保留到秒
        return o.isoformat()
    # 其他不可序列化对象一律转字符串（保险兜底）
    return str(o)


async def log_event(source: str, message: str, meta: Dict[str, Any]) -> None:
    """
    事件日志：写入 event_log(source TEXT, message TEXT, meta JSONB, created_at DEFAULT now())
    注意：使用 text(...) 生成可执行语句，避免 ObjectNotExecutableError。
    """
    payload = json.dumps(meta, ensure_ascii=False, default=_json_default)
    async with _elog_conn() as conn:
        await conn.execute(
            text("INSERT INTO event_log(source, message, meta) VALUES (:s, :m, :j)"),
            {"s": source, "m": message, "j": payload},
        )


async def log_error(source: str, message: str, meta: Dict[str, Any]) -> None:
    """
    错误日志：写入 event_error_log，同上。
    """
    payload = json.dumps(meta, ensure_ascii=False, default=_json_default)
    async with _elog_conn() as conn:
        await conn.execute(
            text("INSERT INTO event_error_log(source, message, meta) VALUES (:s, :m, :j)"),
            {"s": source, "m": message, "j": payload},
        )
