# app/pms/suppliers/repos/supplier_repo.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session, selectinload

from app.models.supplier import Supplier
from app.models.supplier_contact import SupplierContact


def list_suppliers(
    db: Session,
    *,
    active: Optional[bool] = None,
    q: Optional[str] = None,
) -> List[Supplier]:
    query = db.query(Supplier).options(selectinload(Supplier.contacts))

    if active is not None:
        query = query.filter(Supplier.active == active)

    if q and q.strip():
        pat = f"%{q.strip()}%"

        base_match = or_(
            Supplier.name.ilike(pat),
            Supplier.code.ilike(pat),
        )

        contact_match = exists().where(
            (SupplierContact.supplier_id == Supplier.id)
            & (
                SupplierContact.name.ilike(pat)
                | SupplierContact.phone.ilike(pat)
                | SupplierContact.email.ilike(pat)
                | SupplierContact.wechat.ilike(pat)
            )
        )

        query = query.filter(or_(base_match, contact_match))

    return query.order_by(Supplier.id).all()


def list_suppliers_basic(
    db: Session,
    *,
    active: Optional[bool] = True,
    q: Optional[str] = None,
) -> List[Supplier]:
    query = db.query(Supplier)

    if active is not None:
        query = query.filter(Supplier.active == active)

    if q and q.strip():
        pat = f"%{q.strip()}%"
        query = query.filter(or_(Supplier.name.ilike(pat), Supplier.code.ilike(pat)))

    return query.order_by(Supplier.id).all()


def get_supplier_with_contacts(db: Session, supplier_id: int) -> Supplier | None:
    return (
        db.query(Supplier)
        .options(selectinload(Supplier.contacts))
        .filter(Supplier.id == int(supplier_id))
        .one_or_none()
    )


def create_supplier(
    db: Session,
    *,
    name: str,
    code: str,
    website: Optional[str],
    active: bool,
) -> Supplier:
    supplier = Supplier(
        name=name,
        code=code,
        website=website,
        active=bool(active),
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def save_supplier(db: Session, supplier: Supplier) -> Supplier:
    db.commit()
    db.refresh(supplier)
    return supplier
