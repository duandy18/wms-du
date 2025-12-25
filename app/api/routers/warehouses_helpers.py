# app/api/routers/warehouses_helpers.py
from __future__ import annotations

from typing import Any, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.user_service import AuthorizationError, UserService
from app.api.routers.warehouses_schemas import WarehouseOut


def check_perm(db: Session, current_user: Any, required: List[str]) -> None:
    """
    仓库模块权限检查入口。
    复用 stores 模块的 RBAC：config.store.read / config.store.write。
    """
    svc = UserService(db)
    try:
        svc.check_permission(current_user, required)
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized.")


def row_to_warehouse(row: Any) -> WarehouseOut:
    return WarehouseOut(
        id=row["id"],
        name=row["name"],
        code=row.get("code"),
        active=row.get("active", True),
        address=row.get("address"),
        contact_name=row.get("contact_name"),
        contact_phone=row.get("contact_phone"),
        area_sqm=row.get("area_sqm"),
    )
