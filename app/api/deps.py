# app/api/deps.py
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.db.session import get_async_session as _get_async_session
from app.services.order_service import OrderService
from app.services.user_service import UserService


# ---------------------------
# 异步 Session 依赖（业务用）
# ---------------------------


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    统一走 app.db.session 里的 AsyncSession 工厂。
    """
    async for session in _get_async_session():
        yield session
        break


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖友好的包装：直接 yield AsyncSession。
    """
    async with get_async_session() as session:
        yield session


# ---------------------------
# 当前用户依赖（严格版）
# ---------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    严格版当前用户：

    - 必须带 Authorization: Bearer <token>
    - token 无效 / 过期 → 401
    - 用户 inactive → 403
    """
    token = (token or "").strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    svc = UserService(db)
    user = svc.get_user_from_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


# ---------------------------
# 其他依赖
# ---------------------------


async def get_order_service() -> OrderService:
    """
    OrderService 不持有状态，简单返回类实例。
    """
    return OrderService()


__all__ = (
    "get_async_session",
    "get_session",
    "get_current_user",
    "get_order_service",
)
