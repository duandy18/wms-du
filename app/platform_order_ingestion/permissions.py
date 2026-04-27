# app/platform_order_ingestion/permissions.py
# Module boundary: platform order ingestion uses its own page-scoped permissions.
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.user.services.user_service import AuthorizationError, UserService

PLATFORM_ORDER_INGESTION_READ_PERMISSION = "page.platform_order_ingestion.read"
PLATFORM_ORDER_INGESTION_WRITE_PERMISSION = "page.platform_order_ingestion.write"


def _require_permission(db: Session, current_user: Any, permission_name: str) -> None:
    svc = UserService(db)
    try:
        svc.check_permission(current_user, [permission_name])
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized.")


def require_platform_order_ingestion_read(db: Session, current_user: Any) -> None:
    _require_permission(db, current_user, PLATFORM_ORDER_INGESTION_READ_PERMISSION)


def require_platform_order_ingestion_write(db: Session, current_user: Any) -> None:
    _require_permission(db, current_user, PLATFORM_ORDER_INGESTION_WRITE_PERMISSION)


__all__ = [
    "PLATFORM_ORDER_INGESTION_READ_PERMISSION",
    "PLATFORM_ORDER_INGESTION_WRITE_PERMISSION",
    "require_platform_order_ingestion_read",
    "require_platform_order_ingestion_write",
]
