# app/services/stock/retry.py
from __future__ import annotations

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession


async def exec_retry(session: AsyncSession, stmt, params=None):
    """
    统一执行器：对短暂锁冲突做指数退避，不改变隔离级别。
    """
    import asyncio
    import random

    base, mx = 0.03, 0.35
    for i in range(24):
        try:
            return await (session.execute(stmt) if params is None else session.execute(stmt, params))
        except OperationalError as e:
            msg = (str(e) or "").lower()
            if ("database is locked" not in msg and "database is busy" not in msg) or i >= 23:
                raise
            backoff = min(mx, base * (1.8 ** (i + 1)))
            await asyncio.sleep(backoff * (0.6 + 0.4 * random.random()))
