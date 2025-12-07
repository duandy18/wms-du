# app/services/uow.py
"""
Unit of Work（UoW）——统一管理 SQLAlchemy 会话的生命周期与事务边界。

特性：
- 同步与异步两套实现：UnitOfWork / AsyncUnitOfWork
- with / async with 语法：
    with UnitOfWork(SessionLocal) as uow:
        # 使用 uow.session 执行业务
    async with AsyncUnitOfWork(async_sessionmaker) as uow:
        # 使用 uow.session 执行业务
- 退出上下文：
    - 有异常 -> rollback
    - 无异常 -> commit
    - 始终 close 并清空引用
- 可选 expire_on_commit 开关；提供显式 commit()/rollback() 便捷方法
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

# =============================== 同步 UoW ===============================


class UnitOfWork(AbstractContextManager):
    """
    同步版 UoW（兼容旧用法）：

    with UnitOfWork(SessionLocal) as uow:
        repo = MyRepo(uow.session)
        repo.do_something()
    # 正常退出 -> commit；异常 -> rollback；最后 close
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        expire_on_commit: Optional[bool] = None,
    ) -> None:
        """
        :param session_factory: 同步 Session 工厂，如 SessionLocal
        :param expire_on_commit: 可选地覆盖 session.expire_on_commit
        """
        self._session_factory = session_factory
        self._expire_on_commit = expire_on_commit
        self.session: Session | None = None

    # 进入上下文：创建 Session 并应用配置
    def __enter__(self) -> "UnitOfWork":
        self.session = self._session_factory()
        if self._expire_on_commit is not None:
            try:
                self.session.expire_on_commit = bool(self._expire_on_commit)  # type: ignore[attr-defined]
            except Exception:
                # 部分自定义 SessionFactory 可能无该属性，忽略即可
                pass
        return self

    # 退出上下文：异常则回滚，否则提交；最后关闭并清空引用
    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.session is None:
            return False
        try:
            if exc_type:
                self.session.rollback()
            else:
                self.session.commit()
        finally:
            try:
                self.session.close()
            finally:
                self.session = None
        # False -> 如有异常继续向外抛，由调用方处理
        return False

    # 便捷方法（在某些需要分段提交的场景下有用）
    def commit(self) -> None:
        if self.session is not None:
            self.session.commit()

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()


# =============================== 异步 UoW ===============================


class AsyncUnitOfWork(AbstractAsyncContextManager):
    """
    异步版 UoW：

    async with AsyncUnitOfWork(async_sessionmaker) as uow:
        await svc.do_something(uow.session)
    # 正常退出 -> commit；异常 -> rollback；最后 close
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        *,
        expire_on_commit: Optional[bool] = None,
    ) -> None:
        """
        :param session_factory: 异步 Session 工厂，如 async_sessionmaker(...)
        :param expire_on_commit: 可选地覆盖 session.expire_on_commit
        """
        self._session_factory = session_factory
        self._expire_on_commit = expire_on_commit
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> "AsyncUnitOfWork":
        # 大多数 async_sessionmaker 调用后直接返回 AsyncSession（无需 await）
        self.session = self._session_factory()
        if self._expire_on_commit is not None:
            try:
                self.session.expire_on_commit = bool(self._expire_on_commit)  # type: ignore[attr-defined]
            except Exception:
                pass
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self.session is None:
            return False
        try:
            if exc_type:
                await self.session.rollback()
            else:
                await self.session.commit()
        finally:
            try:
                await self.session.close()
            finally:
                self.session = None
        return False

    async def commit(self) -> None:
        if self.session is not None:
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session is not None:
            await self.session.rollback()
