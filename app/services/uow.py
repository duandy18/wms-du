# app/services/uow.py
"""
Unit of Work（UoW）事务单元封装。
用于统一管理 SQLAlchemy Session 的生命周期：
- __enter__() 打开事务
- __exit__() 自动 commit 或 rollback
"""

from contextlib import AbstractContextManager

from sqlalchemy.orm import Session


class UnitOfWork(AbstractContextManager):
    """Unit of Work 封装，支持 with 上下文语法。"""

    def __init__(self, session_factory):
        """
        :param session_factory: 可调用对象，如 SessionLocal
        """
        self._session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self):
        """进入上下文，创建 Session"""
        self.session = self._session_factory()
        return self

    def __exit__(self, exc_type, exc, tb):
        """退出上下文：
        - 若异常发生则 rollback；
        - 否则 commit；
        - 最后关闭连接。
        """
        if self.session is None:
            return False

        try:
            if exc_type:
                self.session.rollback()
            else:
                self.session.commit()
        finally:
            self.session.close()

        # 返回 False 表示异常仍会被传播（方便外层捕获）
        return False
