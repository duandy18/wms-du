# app/pms/suppliers/routers/suppliers_routes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.models.supplier import Supplier
from app.pms.suppliers.contracts.suppliers import SupplierCreateIn, SupplierOut, SupplierUpdateIn
from app.pms.suppliers.helpers.suppliers import check_perm, contacts_out
from app.pms.suppliers.repos.supplier_repo import (
    create_supplier as repo_create_supplier,
    get_supplier_with_contacts as repo_get_supplier_with_contacts,
    list_suppliers as repo_list_suppliers,
    list_suppliers_basic as repo_list_suppliers_basic,
    save_supplier as repo_save_supplier,
)


class SupplierBasicOut(BaseModel):
    """采购/收货用：供应商基础信息（不带 contacts）"""

    id: int
    name: str
    code: Optional[str] = None
    active: bool


def _to_supplier_out(supplier: Supplier) -> SupplierOut:
    return SupplierOut(
        id=supplier.id,
        name=supplier.name,
        code=supplier.code,
        website=supplier.website,
        active=bool(supplier.active),
        contacts=contacts_out(list(supplier.contacts or [])),
    )


def _to_supplier_basic_out(supplier: Supplier) -> SupplierBasicOut:
    return SupplierBasicOut(
        id=supplier.id,
        name=supplier.name,
        code=supplier.code,
        active=bool(supplier.active),
    )


def register(router: APIRouter) -> None:
    @router.get("/suppliers", response_model=List[SupplierOut])
    def list_suppliers(
        active: Optional[bool] = Query(
            None, description="active=true 仅返回合作中供应商（用于下拉）"
        ),
        q: Optional[str] = Query(None, description="名称/编码/联系人/电话/邮箱/微信 模糊搜索"),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, ["config.store.read"])

        suppliers = repo_list_suppliers(db, active=active, q=q)
        return [_to_supplier_out(s) for s in suppliers]

    @router.get("/suppliers/basic", response_model=List[SupplierBasicOut])
    def list_suppliers_basic(
        active: Optional[bool] = Query(
            True, description="默认仅返回合作中供应商（用于下拉）"
        ),
        q: Optional[str] = Query(None, description="名称/编码 模糊搜索"),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, ["purchase.manage"])

        rows = repo_list_suppliers_basic(db, active=active, q=q)
        return [_to_supplier_basic_out(s) for s in rows]

    @router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
    def create_supplier(
        payload: SupplierCreateIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, ["config.store.write"])

        name = payload.name.strip()
        code = payload.code.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")
        if not code:
            raise HTTPException(status_code=422, detail="code is required")

        website = payload.website.strip() if payload.website and payload.website.strip() else None

        supplier = repo_create_supplier(
            db,
            name=name,
            code=code,
            website=website,
            active=bool(payload.active),
        )

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
        check_perm(db, user, ["config.store.write"])

        supplier = repo_get_supplier_with_contacts(db, supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

        if payload.name is not None:
            n = payload.name.strip()
            if not n:
                raise HTTPException(status_code=422, detail="name is required")
            supplier.name = n

        if payload.code is not None:
            c = payload.code.strip()
            if not c:
                raise HTTPException(status_code=422, detail="code is required")
            supplier.code = c

        if payload.website is not None:
            w = payload.website.strip()
            supplier.website = w or None

        if payload.active is not None:
            supplier.active = bool(payload.active)

        supplier = repo_save_supplier(db, supplier)
        return _to_supplier_out(supplier)
