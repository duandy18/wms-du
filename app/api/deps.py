# app/api/deps.py
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.db.session import get_async_session as _get_async_session
from app.services.order_service import OrderService  # noqa: E402
from app.services.user_service import UserService


# ---------------------------
# 异步 Session 依赖（业务用）
# ---------------------------


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    统一走 app.db.session 里的 AsyncSession 工厂。

    用法（FastAPI 依赖）：
        async def handler(session: AsyncSession = Depends(get_session)): ...
    """
    async for session in _get_async_session():
        # _get_async_session 本身就是 async generator
        yield session
        break  # 理论上只会 yield 一次，这里显式 break 表明意图


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖友好的包装：直接 yield AsyncSession。
    """
    async with get_async_session() as session:
        yield session


# ---------------------------
# 当前用户依赖（RBAC 用）
# ---------------------------

# 标准 OAuth2 Bearer 方案，从 Authorization 头里取 token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


class _TestUser:
    """
    无 token 场景下的匿名用户占位对象。

    - id 固定为 0
    - username="anonymous"
    - role_id=None → 在权限检查时视为“无权限”
    - is_active=False
    """

    def __init__(self) -> None:
        self.id: int = 0
        self.username: str = "anonymous"
        self.role_id: Optional[int] = None
        self.is_active: bool = False

    def __repr__(self) -> str:  # 方便日志调试
        return f"<AnonymousUser id={self.id} username={self.username!r}>"


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    统一的“当前用户”依赖：

    - 有 token：
        - 使用 UserService.get_user_from_token(token) 解析；
        - 无效/过期 → 401；
        - inactive → 403。
    - 无 token：
        - 返回一个匿名 _TestUser（role_id=None），
          在需要权限的接口上会被 check_permission 拒绝，
          不需要权限的接口则可以当作“未登录用户”使用。
    """
    token = (token or "").strip()

    # 无 token：返回匿名用户（用于公开/半公开接口）
    if not token:
        return _TestUser()

    svc = UserService(db)
    user = svc.get_user_from_token(token)
    if not user:
        # token 无效或已过期
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
    目前 OrderService 不持有状态，这里简单返回类即可；
    保留成依赖是为了将来若需要注入配置/适配器时好扩展。
    """
    return OrderService()


__all__ = (
    "get_async_session",
    "get_session",
    "get_current_user",
    "get_order_service",
)
