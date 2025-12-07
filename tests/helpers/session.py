# tests/helpers/session.py
from contextlib import asynccontextmanager


@asynccontextmanager
async def safe_begin(session):
    """
    测试专用的“干净事务”上下文：
    - 若前面做过裸 execute/读操作，先 commit 清掉隐式事务；
    - 再进入 async with session.begin()。
    """
    try:
        await session.commit()
    except Exception:
        # 不在事务中时，commit 无副作用；保持安静即可
        pass
    async with session.begin():
        yield
