# app/api/routers/stores_routes_bindings_helpers.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


def check_store_perm(db: Session, current_user, perms: list[str]) -> None:
    from app.api.routers import stores as stores_router

    stores_router._check_perm(db, current_user, perms)


async def ensure_store_exists(session: AsyncSession, store_id: int) -> None:
    from app.api.routers import stores as stores_router

    await stores_router._ensure_store_exists(session, store_id)


async def ensure_warehouse_exists(
    session: AsyncSession, warehouse_id: int, *, require_active: bool = False
) -> None:
    from app.api.routers import stores as stores_router

    await stores_router._ensure_warehouse_exists(
        session, warehouse_id, require_active=require_active
    )
