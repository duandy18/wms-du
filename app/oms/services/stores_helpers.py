# app/api/routers/stores_helpers.py
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.services.user_service import AuthorizationError, UserService


async def ensure_store_exists(session: AsyncSession, store_id: int) -> None:
    row = await session.execute(
        text(
            """
            SELECT 1
              FROM stores
             WHERE id = :sid
             LIMIT 1
            """
        ),
        {"sid": store_id},
    )
    if row.first() is None:
        raise HTTPException(status_code=404, detail="store not found")


async def ensure_warehouse_exists(
    session: AsyncSession,
    warehouse_id: int,
    *,
    require_active: bool = False,
) -> None:
    """
    校验仓库存在；若 require_active=True，则同时要求 active=TRUE。
    """
    row = await session.execute(
        text(
            """
            SELECT active
              FROM warehouses
             WHERE id = :wid
             LIMIT 1
            """
        ),
        {"wid": warehouse_id},
    )
    rec = row.mappings().first()
    if rec is None:
        raise HTTPException(status_code=404, detail="warehouse not found")

    if require_active and not rec.get("active", True):
        raise HTTPException(status_code=400, detail="warehouse is inactive")


def check_perm(
    db: Session,
    current_user: Any,
    required: list[str],
) -> None:
    """
    统一的 store 配置权限检查入口。
    """
    svc = UserService(db)
    try:
        svc.check_permission(current_user, required)
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized.")
