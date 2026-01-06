# app/api/routers/suppliers_routes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.models.supplier import Supplier
from app.models.supplier_contact import SupplierContact
from app.api.routers.suppliers_schemas import SupplierCreateIn, SupplierOut, SupplierUpdateIn


class SupplierBasicOut(BaseModel):
    """采购/收货用：供应商基础信息（不带 contacts）"""

    id: int
    name: str
    code: Optional[str] = None
    active: bool


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
        from app.api.routers import suppliers as suppliers_router

        suppliers_router._check_perm(db, user, ["config.store.read"])

        # ✅ 避免 N+1：一次性加载 contacts
        query = db.query(Supplier).options(selectinload(Supplier.contacts))

        if active is not None:
            query = query.filter(Supplier.active == active)

        if q and q.strip():
            pat = f"%{q.strip()}%"

            # 搜索：supplier.name / supplier.code
            base_match = or_(
                Supplier.name.ilike(pat),
                Supplier.code.ilike(pat),
            )

            # 搜索：联系人字段（EXISTS 子查询，避免 join 膨胀）
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

        suppliers = query.order_by(Supplier.id).all()

        return [
            SupplierOut(
                id=s.id,
                name=s.name,
                code=s.code,
                website=s.website,
                active=bool(s.active),
                contacts=suppliers_router._contacts_out(list(s.contacts or [])),
            )
            for s in suppliers
        ]

    # ✅ 采购/收货用：供应商基础列表（不带 contacts）
    # - 目的：采购单创建 / 收货作业台下拉
    # - 权限：purchase.manage（避免要求 config.store.read）
    @router.get("/suppliers/basic", response_model=List[SupplierBasicOut])
    def list_suppliers_basic(
        active: Optional[bool] = Query(
            True, description="默认仅返回合作中供应商（用于下拉）"
        ),
        q: Optional[str] = Query(None, description="名称/编码 模糊搜索"),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        from app.api.routers import suppliers as suppliers_router

        suppliers_router._check_perm(db, user, ["purchase.manage"])

        query = db.query(Supplier)

        if active is not None:
            query = query.filter(Supplier.active == active)

        if q and q.strip():
            pat = f"%{q.strip()}%"
            query = query.filter(or_(Supplier.name.ilike(pat), Supplier.code.ilike(pat)))

        rows = query.order_by(Supplier.id).all()

        return [
            SupplierBasicOut(
                id=s.id,
                name=s.name,
                code=s.code,
                active=bool(s.active),
            )
            for s in rows
        ]

    @router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
    def create_supplier(
        payload: SupplierCreateIn,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        from app.api.routers import suppliers as suppliers_router

        suppliers_router._check_perm(db, user, ["config.store.write"])

        name = payload.name.strip()
        code = payload.code.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")
        if not code:
            raise HTTPException(status_code=422, detail="code is required")

        supplier = Supplier(
            name=name,
            code=code,
            website=payload.website.strip()
            if payload.website and payload.website.strip()
            else None,
            active=bool(payload.active),
        )

        db.add(supplier)
        db.commit()
        db.refresh(supplier)

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
        from app.api.routers import suppliers as suppliers_router

        suppliers_router._check_perm(db, user, ["config.store.write"])

        supplier = (
            db.query(Supplier)
            .options(selectinload(Supplier.contacts))
            .get(supplier_id)
        )
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

        db.commit()
        db.refresh(supplier)

        return SupplierOut(
            id=supplier.id,
            name=supplier.name,
            code=supplier.code,
            website=supplier.website,
            active=bool(supplier.active),
            contacts=suppliers_router._contacts_out(list(supplier.contacts or [])),
        )
