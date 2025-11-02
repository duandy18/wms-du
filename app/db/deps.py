# app/db/deps.py
"""
统一数据库依赖（薄转发到 app.db.session）：
- get_db           → 同步 Session（yield）
- get_async_session→ 异步 AsyncSession（yield）
- get_db_session   → 同步别名，便于旧代码依赖
"""

from __future__ import annotations
from typing import Generator, AsyncGenerator

try:
    # 项目内统一的会话工厂（推荐）
    from app.db.session import get_db as _get_db  # 同步 generator[yield Session]
    from app.db.session import get_session as _get_async_session  # 异步 generator[yield AsyncSession]
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "app.db.deps 依赖 app.db.session 中的 get_db / get_session。"
        "请确认 app/db/session.py 存在并导出了对应函数。"
    ) from e


# ---- 同步 Session 依赖 ----
def get_db() -> Generator["Session", None, None]:
    """
    用法：def endpoint(db: Session = Depends(get_db)): ...
    直接转发 app.db.session.get_db
    """
    yield from _get_db()  # type: ignore[misc]


# 旧名字兼容
get_db_session = get_db


# ---- 异步 AsyncSession 依赖 ----
async def get_async_session() -> AsyncGenerator["AsyncSession", None]:
    """
    用法：async def endpoint(session: AsyncSession = Depends(get_async_session)): ...
    直接转发 app.db.session.get_session
    """
    async for s in _get_async_session():  # type: ignore[misc]
        yield s
