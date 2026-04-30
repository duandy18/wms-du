# app/pms/suppliers/routers/supplier_contacts.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.pms.suppliers.contracts.suppliers import (
    SupplierContactCreateIn,
    SupplierContactOut,
    SupplierContactUpdateIn,
)
from app.pms.suppliers.repos.supplier_contact_repo import (
    clear_primary_contacts as repo_clear_primary_contacts,
)
from app.pms.suppliers.repos.supplier_contact_repo import (
    create_contact as repo_create_contact,
)
from app.pms.suppliers.repos.supplier_contact_repo import (
    delete_contact as repo_delete_contact,
)
from app.pms.suppliers.repos.supplier_contact_repo import (
    get_contact as repo_get_contact,
)
from app.pms.suppliers.repos.supplier_contact_repo import (
    get_supplier as repo_get_supplier,
)
from app.pms.suppliers.repos.supplier_contact_repo import (
    save_contact as repo_save_contact,
)
from app.pms.suppliers.helpers.suppliers import check_perm

router = APIRouter(tags=["supplier-contacts"])


def _to_out(c) -> SupplierContactOut:
    return SupplierContactOut(
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


def _trim_or_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    t = v.strip()
    return t if t else None


@router.post(
    "/suppliers/{supplier_id}/contacts",
    response_model=SupplierContactOut,
    status_code=status.HTTP_201_CREATED,
    name="supplier_create_contact",
)
def create_contact(
    supplier_id: int = Path(..., ge=1),
    payload: SupplierContactCreateIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_perm(db, user, ["page.pms.write"])

    supplier = repo_get_supplier(db, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    phone = _trim_or_none(payload.phone)
    wechat = _trim_or_none(payload.wechat)
    role = (payload.role or "other").strip() or "other"
    email = str(payload.email).strip() if payload.email else None

    if payload.is_primary:
        repo_clear_primary_contacts(db, supplier_id)

    contact = repo_create_contact(
        db,
        supplier_id=supplier_id,
        name=name,
        phone=phone,
        email=email,
        wechat=wechat,
        role=role,
        is_primary=payload.is_primary,
        active=payload.active,
    )
    return _to_out(contact)


@router.patch(
    "/supplier-contacts/{contact_id}",
    response_model=SupplierContactOut,
    name="supplier_update_contact",
)
def update_contact(
    contact_id: int = Path(..., ge=1),
    payload: SupplierContactUpdateIn = ...,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_perm(db, user, ["page.pms.write"])

    contact = repo_get_contact(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if payload.is_primary is True:
        repo_clear_primary_contacts(db, contact.supplier_id)

    data = payload.model_dump(exclude_unset=True)

    if "name" in data:
        n = (data["name"] or "").strip()
        if not n:
            raise HTTPException(status_code=422, detail="name is required")
        contact.name = n

    if "phone" in data:
        contact.phone = _trim_or_none(data["phone"])

    if "email" in data:
        contact.email = str(data["email"]).strip() if data["email"] else None

    if "wechat" in data:
        contact.wechat = _trim_or_none(data["wechat"])

    if "role" in data:
        contact.role = (data["role"] or "other").strip() or "other"

    if "is_primary" in data:
        contact.is_primary = bool(data["is_primary"])

    if "active" in data:
        contact.active = bool(data["active"])

    contact = repo_save_contact(db, contact)
    return _to_out(contact)


@router.delete(
    "/supplier-contacts/{contact_id}",
    status_code=status.HTTP_200_OK,
    name="supplier_delete_contact",
)
def delete_contact(
    contact_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    check_perm(db, user, ["page.pms.write"])

    contact = repo_get_contact(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    repo_delete_contact(db, contact)
    return {"ok": True}
