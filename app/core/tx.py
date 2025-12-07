# app/core/tx.py
from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


class ProbeDone(Exception):
    """用于 probe 事务块的控制流中断。"""


@asynccontextmanager
async def tx_probe(session: AsyncSession):
    """
    Probe 事务：使用保存点包裹，被测函数成功后回滚保存点。
    """
    try:
        async with session.begin_nested():
            yield
            # 走到这里表示被测函数未抛异常，触发保存点回滚
            raise ProbeDone()
    except ProbeDone:
        return


@asynccontextmanager
async def tx_commit(session: AsyncSession):
    """
    Commit 事务：正常 begin/commit。
    """
    async with session.begin():
        yield


class TxManager:
    """
    统一的事务执行器：根据 probe 标志选择事务上下文。
    Handler 内部不得控事务。
    """

    @staticmethod
    async def run(session: AsyncSession, *, probe: bool, fn, **kwargs):
        ctx = tx_probe if probe else tx_commit
        async with ctx(session):
            return await fn(session=session, **kwargs)
