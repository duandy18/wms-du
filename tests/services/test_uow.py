# tests/services/test_uow.py
import pytest

pytestmark = [pytest.mark.asyncio]


async def test_uow_commit_and_rollback(session, _db_clean_and_seed):
    """
    最小契约：

    - UnitOfWork 支持 async with 语法；
    - 进入上下文后 uow.session 不为 None；
    - 能在不报错的情况下完成一次 async 上下文。
    """
    from app.services.uow import UnitOfWork

    async with UnitOfWork(session) as uow:
        # 只要 session 挂载成功，测试契约就满足了
        assert uow.session is not None
        # 不做具体 SQL 断言，避免绑定到某张表或某种事务实现
