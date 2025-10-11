# app/db/session.py
# 统一的同步/异步会话工厂 + FastAPI 依赖（get_db / get_session）
import os
from typing import Generator, AsyncGenerator

from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import create_sync_engine, create_async_engine_safe

# CI 会设置 DATABASE_URL；本地回退到 sqlite+aiosqlite
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///dev.db")

# 同步引擎 + Session
engine = create_sync_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

# 异步引擎 + AsyncSession
async_engine = create_async_engine_safe(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 为兼容历史引用（有的模块期望 async_session_maker）
async_session_maker = AsyncSessionLocal  # type: ignore[assignment]


# FastAPI 依赖注入（同步）
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# FastAPI 依赖注入（异步）
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # 会在 async with 退出时自动关闭，这里留空保障语义清晰
            pass
