# app/services/uow.py
"""
Unit of Work（UoW）——统一管理 SQLAlchemy 会话的生命周期与事务边界。

特点：

- 支持同步 / 异步双栈：
    * 同步：
        with UnitOfWork(SessionLocal) as uow:
            uow.session  # Session
    * 异步：
        async with UnitOfWork(async_session) as uow:
            uow.session  # AsyncSession

- 传参模式：
    * session 工厂：
        UnitOfWork(SessionLocal)
        UnitOfWork(async_sessionmaker)
    * 现成 session：
        UnitOfWork(session)         # Session
        UnitOfWork(async_session)   # AsyncSession

- 事务语义：
    * 无异常 -> commit
    * 有异常 -> rollback
    * 只有在 UoW 自己创建的 session 上负责 close；
      对于外部传入的现成 session，不负责关闭。
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any, Awaitable, Callable, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

SyncSessionFactory = Callable[[], Session]
AsyncSessionFactory = Callable[[], Union[AsyncSession, Awaitable[AsyncSession]]]
SessionOrFactory = Union[Session, AsyncSession, SyncSessionFactory, AsyncSessionFactory]


class UnitOfWork(AbstractContextManager, AbstractAsyncContextManager):
    """
    统一版 UoW。

    支持两种使用方式：

    1）同步：
        with UnitOfWork(SessionLocal) as uow:
            repo = Repo(uow.session)
            ...

    2）异步：
        async with UnitOfWork(async_session) as uow:
            await svc.do_something(uow.session)

    对于测试 `test_uow_commit_and_rollback`：
        async with UnitOfWork(session) as uow:
            assert uow.session is not None
    """

    def __init__(
        self,
        session_or_factory: SessionOrFactory,
        *,
        expire_on_commit: Optional[bool] = None,
    ) -> None:
        self._session_or_factory: SessionOrFactory = session_or_factory
        self._expire_on_commit = expire_on_commit

        self.session: Union[Session, AsyncSession, None] = None
        self._owns_session: bool = False  # 是否由 UoW 自己创建并负责关闭

    # ------------------------ 内部工具方法 ------------------------

    def _apply_expire_on_commit(self) -> None:
        if self._expire_on_commit is None or self.session is None:
            return
        try:
            # 同步 / 异步 Session 都可能有该属性
            setattr(self.session, "expire_on_commit", bool(self._expire_on_commit))  # type: ignore[attr-defined]
        except Exception:
            # 某些自定义 Session 实现可能不支持，静默忽略
            pass

    # ------------------------ 同步上下文 ------------------------

    def __enter__(self) -> "UnitOfWork":
        # 已有 Session：直接复用
        if isinstance(self._session_or_factory, Session):
            self.session = self._session_or_factory
            self._owns_session = False
        else:
            # 认为是同步 Session 工厂
            factory = self._session_or_factory  # type: ignore[assignment]
            if not callable(factory):
                raise TypeError("同步上下文下，UnitOfWork 期望传入 Session 或 Session 工厂。")
            self.session = factory()  # type: ignore[call-arg]
            self._owns_session = True

        if not isinstance(self.session, Session):
            raise TypeError("使用 with UnitOfWork(...) 时，需要同步 Session。")

        self._apply_expire_on_commit()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.session is None or not isinstance(self.session, Session):
            return False

        try:
            if exc_type:
                self.session.rollback()
            else:
                self.session.commit()
        finally:
            if self._owns_session:
                try:
                    self.session.close()
                finally:
                    self.session = None
        # False -> 异常继续向外抛
        return False

    # ------------------------ 异步上下文 ------------------------

    async def __aenter__(self) -> "UnitOfWork":
        # 已有 AsyncSession：直接复用
        if isinstance(self._session_or_factory, AsyncSession):
            self.session = self._session_or_factory
            self._owns_session = False
        else:
            # 认为是异步 Session 工厂
            factory = self._session_or_factory  # type: ignore[assignment]
            if not callable(factory):
                raise TypeError("异步上下文下，UnitOfWork 期望传入 AsyncSession 或 async_session 工厂。")
            maybe_session: Any = factory()  # type: ignore[call-arg]

            if isinstance(maybe_session, AsyncSession):
                self.session = maybe_session
            else:
                # 兼容 async_sessionmaker 返回 awaitable 的情况
                self.session = await maybe_session  # type: ignore[assignment]

            self._owns_session = True

        if not isinstance(self.session, AsyncSession):
            raise TypeError("使用 async with UnitOfWork(...) 时，需要 AsyncSession。")

        self._apply_expire_on_commit()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self.session is None or not isinstance(self.session, AsyncSession):
            return False

        try:
            if exc_type:
                await self.session.rollback()
            else:
                await self.session.commit()
        finally:
            if self._owns_session:
                try:
                    await self.session.close()
                finally:
                    self.session = None
        return False

    # ------------------------ 便捷方法 ------------------------

    def commit(self) -> None:
        """
        同步场景下的显式提交。
        """
        if isinstance(self.session, Session):
            self.session.commit()

    def rollback(self) -> None:
        """
        同步场景下的显式回滚。
        """
        if isinstance(self.session, Session):
            self.session.rollback()

    async def commit_async(self) -> None:
        """
        异步场景下的显式提交。
        """
        if isinstance(self.session, AsyncSession):
            await self.session.commit()

    async def rollback_async(self) -> None:
        """
        异步场景下的显式回滚。
        """
        if isinstance(self.session, AsyncSession):
            await self.session.rollback()


class AsyncUnitOfWork(UnitOfWork):
    """
    兼容旧命名：AsyncUnitOfWork(async_session_or_factory)

    实际行为完全复用 UnitOfWork，只用于语义上的区分。
    """
    pass
