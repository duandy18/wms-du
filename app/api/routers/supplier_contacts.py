# app/api/routers/supplier_contacts.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.supplier import Supplier
from app.models.supplier_contact import SupplierContact
from app.services.user_service import AuthorizationError, UserService

router = APIRouter(tags=["supplier-contacts"])


# -----------------------
# Schemas
# -----------------------


class SupplierContactOut(BaseModel):
    id: int
    supplier_id: int
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    wechat: Optional[str] = None
    role: str
    is_primary: bool
    active: bool


class SupplierContactCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[str] = Field(None, max_length=64)
    role: str = Field(default="other", max_length=32)  # purchase/billing/shipping/after_sales/other
    is_primary: bool = False
    active: bool = True


class SupplierContactUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[str] = Field(None, max_length=64)
    role: Optional[str] = Field(None, max_length=32)
    is_primary: Optional[bool] = None
    active: Optional[bool] = None


def _check_perm(db: Session, user) -> None:
    svc = UserService(db)
    try:
        svc.check_permission(user, ["config.store.write"])
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized")


def _to_out(c: SupplierContact) -> SupplierContactOut:
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


# -----------------------
# Routes
# -----------------------


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
    _check_perm(db, user)

    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    phone = _trim_or_none(payload.phone)
    wechat = _trim_or_none(payload.wechat)
    role = (payload.role or "other").strip() or "other"

    # 主联系人：先清空旧主，再设置新主
    if payload.is_primary:
        db.query(SupplierContact).filter(
            SupplierContact.supplier_id == supplier_id,
            SupplierContact.is_primary.is_(True),
        ).update({"is_primary": False}, synchronize_session=False)

    contact = SupplierContact(
        supplier_id=supplier_id,
        name=name,
        phone=phone,
        email=str(payload.email).strip() if payload.email else None,
        wechat=wechat,
        role=role,
        is_primary=payload.is_primary,
        active=payload.active,
    )

    db.add(contact)
    db.commit()
    db.refresh(contact)

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
    _check_perm(db, user)

    contact = db.query(SupplierContact).get(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # 如果要把这个联系人设为主联系人：先清空同 supplier 的旧主
    if payload.is_primary is True:
        db.query(SupplierContact).filter(
            SupplierContact.supplier_id == contact.supplier_id,
            SupplierContact.is_primary.is_(True),
        ).update({"is_primary": False}, synchronize_session=False)

    data = payload.dict(exclude_unset=True)

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
        # 允许取消主联系人（False）
        contact.is_primary = bool(data["is_primary"])

    if "active" in data:
        contact.active = bool(data["active"])

    db.commit()
    db.refresh(contact)

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
    _check_perm(db, user)

    contact = db.query(SupplierContact).get(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    db.delete(contact)
    db.commit()

    return {"ok": True}
