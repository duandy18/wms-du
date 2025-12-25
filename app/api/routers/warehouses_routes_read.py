# app/api/routers/warehouses_routes_read.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.warehouses_helpers import check_perm, row_to_warehouse
from app.api.routers.warehouses_schemas import WarehouseDetailOut, WarehouseListOut
from app.db.deps import get_db


def register(router: APIRouter) -> None:
    @router.get("/warehouses", response_model=WarehouseListOut)
    async def list_warehouses(
        active: Optional[bool] = Query(
            None,
            description="是否只返回启用/停用仓库；active=true 专供店铺绑定下拉使用。",
        ),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseListOut:
        check_perm(db, current_user, ["config.store.read"])

        where_clause = ""
        params: Dict[str, Any] = {}
        if active is not None:
            where_clause = "WHERE w.active = :active"
            params["active"] = active

        sql = text(
            f"""
            SELECT
              w.id,
              w.name,
              w.code,
              w.active,
              w.address,
              w.contact_name,
              w.contact_phone,
              w.area_sqm
            FROM warehouses AS w
            {where_clause}
            ORDER BY w.id
            """
        )

        result = await session.execute(sql, params)
        rows = result.mappings().all()
        data = [row_to_warehouse(row) for row in rows]
        return WarehouseListOut(ok=True, data=data)

    @router.get("/warehouses/{warehouse_id}", response_model=WarehouseDetailOut)
    async def get_warehouse(
        warehouse_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseDetailOut:
        check_perm(db, current_user, ["config.store.read"])

        sql = text(
            """
            SELECT
              w.id,
              w.name,
              w.code,
              w.active,
              w.address,
              w.contact_name,
              w.contact_phone,
              w.area_sqm
            FROM warehouses AS w
            WHERE w.id = :wid
            LIMIT 1
            """
        )

        row = (await session.execute(sql, {"wid": warehouse_id})).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="warehouse not found")

        return WarehouseDetailOut(ok=True, data=row_to_warehouse(row))
