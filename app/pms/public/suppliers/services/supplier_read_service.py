# app/pms/public/suppliers/services/supplier_read_service.py
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.pms.suppliers.models.supplier import Supplier
from app.pms.public.suppliers.contracts.supplier_basic import SupplierBasic
from app.pms.suppliers.repos.supplier_repo import (
    list_suppliers_basic as repo_list_suppliers_basic,
)


class SupplierReadService:
    """
    PMS public supplier read service。

    定位：
    - 供其他模块读取 PMS 供应商最小事实
    - 不承载 contacts 聚合
    - 不承载写入语义
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_basic(
        self,
        *,
        active: Optional[bool] = True,
        q: Optional[str] = None,
    ) -> list[SupplierBasic]:
        rows = repo_list_suppliers_basic(self.db, active=active, q=q)
        return [self._to_basic(x) for x in rows]

    @staticmethod
    def _to_basic(supplier: Supplier) -> SupplierBasic:
        return SupplierBasic(
            id=int(supplier.id),
            name=str(supplier.name),
            code=supplier.code,
            active=bool(supplier.active),
        )
