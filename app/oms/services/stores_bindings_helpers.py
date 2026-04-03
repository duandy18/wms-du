# app/oms/services/stores_bindings_helpers.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.oms.services.stores_helpers import (
    check_perm,
    ensure_store_exists as _ensure_store_exists,
    ensure_warehouse_exists as _ensure_warehouse_exists,
)


def check_store_perm(db: Session, current_user, perms: list[str]) -> None:
    check_perm(db, current_user, perms)


async def ensure_store_exists(session: AsyncSession, store_id: int) -> None:
    await _ensure_store_exists(session, store_id)


async def ensure_warehouse_exists(
    session: AsyncSession, warehouse_id: int, *, require_active: bool = False
) -> None:
    await _ensure_warehouse_exists(
        session, warehouse_id, require_active=require_active
    )
