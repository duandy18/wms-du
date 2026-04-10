# app/pms/suppliers/routers/suppliers_routes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.pms.suppliers.models.supplier import Supplier
from app.pms.suppliers.contracts.suppliers import SupplierCreateIn, SupplierOut, SupplierUpdateIn
from app.pms.suppliers.helpers.suppliers import check_perm, contacts_out
from app.pms.suppliers.repos.supplier_repo import (
    create_supplier as repo_create_supplier,
    get_supplier_with_contacts as repo_get_supplier_with_contacts,
    list_suppliers as repo_list_suppliers,
    save_supplier as repo_save_supplier,
)


def _to_supplier_out(supplier: Supplier) -> SupplierOut:
    return SupplierOut(
        id=supplier.id,
        name=supplier.name,
        code=supplier.code,
        website=supplier.website,
        active=bool(supplier.active),
        contacts=contacts_out(list(supplier.contacts or [])),
    )


def _normalize_name(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise HTTPException(status_code=422, detail="name is required")
    return v


def _normalize_code(value: str) -> str:
    v = (value or "").strip().upper()
    if not v:
        raise HTTPException(status_code=422, detail="code is required")
    return v


def _normalize_website(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    return v or None


def _raise_supplier_integrity(db: Session, exc: IntegrityError) -> None:
    db.rollback()
    raw = str(getattr(exc, "orig", exc)).lower()

    if "uq_suppliers_code" in raw or ("unique" in raw and "code" in raw):
        raise HTTPException(status_code=409, detail="供应商编码已存在")
    if "uq_suppliers_name" in raw or ("unique" in raw and "name" in raw):
        raise HTTPException(status_code=409, detail="供应商名称已存在")

    raise HTTPException(status_code=400, detail=f"DB integrity error: {getattr(exc, 'orig', exc)}")


def register(router: APIRouter) -> None:
    @router.get("/suppliers", response_model=List[SupplierOut])
    def list_suppliers(
        active: Optional[bool] = Query(
            None, description="active=true 仅返回合作中供应商（owner 页面使用）"
        ),
        q: Optional[str] = Query(None, description="名称/编码/联系人/电话/邮箱/微信 模糊搜索"),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, ["page.pms.read"])

        suppliers = repo_list_suppliers(db, active=active, q=q)
        return [_to_supplier_out(s) for s in suppliers]

    @router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
    def create_supplier(
        payload: SupplierCreateIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, ["page.pms.write"])

        name = _normalize_name(payload.name)
        code = _normalize_code(payload.code)
        website = _normalize_website(payload.website)

        try:
            supplier = repo_create_supplier(
                db,
                name=name,
                code=code,
                website=website,
                active=bool(payload.active),
            )
        except IntegrityError as exc:
            _raise_supplier_integrity(db, exc)

        return SupplierOut(
            id=supplier.id,
            name=supplier.name,
            code=supplier.code,
            website=supplier.website,
            active=bool(supplier.active),
            contacts=[],
        )

    @router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
    def update_supplier(
        supplier_id: int = Path(..., ge=1),
        payload: SupplierUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, ["page.pms.write"])

        supplier = repo_get_supplier_with_contacts(db, supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        if payload.name is not None:
            supplier.name = _normalize_name(payload.name)

        if payload.code is not None:
            supplier.code = _normalize_code(payload.code)

        if payload.website is not None:
            supplier.website = _normalize_website(payload.website)

        if payload.active is not None:
            supplier.active = bool(payload.active)

        try:
            supplier = repo_save_supplier(db, supplier)
        except IntegrityError as exc:
            _raise_supplier_integrity(db, exc)

        return _to_supplier_out(supplier)
