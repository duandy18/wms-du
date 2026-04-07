# app/pms/suppliers/repos/supplier_contact_repo.py
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.supplier import Supplier
from app.models.supplier_contact import SupplierContact


def get_supplier(db: Session, supplier_id: int) -> Supplier | None:
    return db.query(Supplier).get(int(supplier_id))


def clear_primary_contacts(db: Session, supplier_id: int) -> None:
    db.query(SupplierContact).filter(
        SupplierContact.supplier_id == int(supplier_id),
        SupplierContact.is_primary.is_(True),
    ).update({"is_primary": False}, synchronize_session=False)


def create_contact(
    db: Session,
    *,
    supplier_id: int,
    name: str,
    phone: str | None,
    email: str | None,
    wechat: str | None,
    role: str,
    is_primary: bool,
    active: bool,
) -> SupplierContact:
    contact = SupplierContact(
        supplier_id=int(supplier_id),
        name=name,
        phone=phone,
        email=email,
        wechat=wechat,
        role=role,
        is_primary=bool(is_primary),
        active=bool(active),
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def get_contact(db: Session, contact_id: int) -> SupplierContact | None:
    return db.query(SupplierContact).get(int(contact_id))


def save_contact(db: Session, contact: SupplierContact) -> SupplierContact:
    db.commit()
    db.refresh(contact)
    return contact


def delete_contact(db: Session, contact: SupplierContact) -> None:
    db.delete(contact)
    db.commit()
