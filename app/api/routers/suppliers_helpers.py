# app/api/routers/suppliers_helpers.py
from __future__ import annotations

from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.supplier_contact import SupplierContact
from app.services.user_service import AuthorizationError, UserService

from app.api.routers.suppliers_schemas import SupplierContactOut


def check_perm(db: Session, user, perms: List[str]) -> None:
    svc = UserService(db)
    try:
        svc.check_permission(user, perms)
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized")


def contacts_out(contacts: List[SupplierContact]) -> List[SupplierContactOut]:
    # 稳定排序：主联系人优先，其次 id
    ordered = sorted(contacts, key=lambda c: (not bool(c.is_primary), c.id))
    return [
        SupplierContactOut(
            id=c.id,
            supplier_id=c.supplier_id,
            name=c.name,
            phone=c.phone,
            email=c.email,
            wechat=c.wechat,
            role=c.role,
            is_primary=bool(c.is_primary),
            active=bool(c.active),
        )
        for c in ordered
    ]
