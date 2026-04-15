# app/pms/public/suppliers/services/supplier_read_service.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
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
    - 同时支持 sync Session 与 AsyncSession
    """

    def __init__(self, db: Session | AsyncSession) -> None:
        self.db = db

    def _require_sync_db(self) -> Session:
        if isinstance(self.db, AsyncSession):
            raise TypeError("SupplierReadService sync API requires Session, got AsyncSession")
        if not isinstance(self.db, Session):
            raise TypeError(f"SupplierReadService expected Session, got {type(self.db)!r}")
        return self.db

    def _require_async_db(self) -> AsyncSession:
        if not isinstance(self.db, AsyncSession):
            raise TypeError("SupplierReadService async API requires AsyncSession")
        return self.db

    def list_basic(
        self,
        *,
        active: Optional[bool] = True,
        q: Optional[str] = None,
    ) -> list[SupplierBasic]:
        db = self._require_sync_db()
        rows = repo_list_suppliers_basic(db, active=active, q=q)
        return [self._to_basic(x) for x in rows]

    async def alist_basic(
        self,
        *,
        active: Optional[bool] = True,
        q: Optional[str] = None,
    ) -> list[SupplierBasic]:
        db = self._require_async_db()

        stmt = select(Supplier)

        if active is not None:
            stmt = stmt.where(Supplier.active.is_(bool(active)))

        qv = (q or "").strip()
        if qv:
            like = f"%{qv}%"
            stmt = stmt.where(
                or_(
                    Supplier.name.ilike(like),
                    Supplier.code.ilike(like),
                )
            )

        stmt = stmt.order_by(Supplier.id.asc())

        rows = (await db.execute(stmt)).scalars().all()
        return [self._to_basic(x) for x in rows]

    async def aget_basic_by_id(self, *, supplier_id: int) -> SupplierBasic | None:
        db = self._require_async_db()

        stmt = (
            select(Supplier)
            .where(Supplier.id == int(supplier_id))
            .limit(1)
        )
        obj = (await db.execute(stmt)).scalars().first()
        if obj is None:
            return None
        return self._to_basic(obj)

    @staticmethod
    def _to_basic(supplier: Supplier) -> SupplierBasic:
        return SupplierBasic(
            id=int(supplier.id),
            name=str(supplier.name),
            code=supplier.code,
            active=bool(supplier.active),
        )
