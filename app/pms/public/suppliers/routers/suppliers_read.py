# app/pms/public/suppliers/routers/suppliers_read.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.public.suppliers.contracts.supplier_basic import SupplierBasic
from app.pms.public.suppliers.services.supplier_read_service import SupplierReadService

router = APIRouter(prefix="/public/suppliers", tags=["pms-public-suppliers"])


def get_supplier_read_service(db: Session = Depends(get_db)) -> SupplierReadService:
    return SupplierReadService(db)


@router.get("", response_model=list[SupplierBasic], status_code=status.HTTP_200_OK)
def list_public_suppliers(
    active: Optional[bool] = Query(
        True,
        description="默认仅返回合作中供应商（用于跨模块下拉）",
    ),
    q: Optional[str] = Query(
        None,
        description="名称/编码 模糊搜索",
    ),
    service: SupplierReadService = Depends(get_supplier_read_service),
) -> list[SupplierBasic]:
    return service.list_basic(active=active, q=q)
