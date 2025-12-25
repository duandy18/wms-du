# app/api/routers/warehouses_routes_write.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.warehouses_helpers import check_perm, row_to_warehouse
from app.api.routers.warehouses_schemas import (
    WarehouseCreateIn,
    WarehouseCreateOut,
    WarehouseUpdateIn,
    WarehouseUpdateOut,
)
from app.db.deps import get_db


def register(router: APIRouter) -> None:
    @router.post(
        "/warehouses",
        status_code=status.HTTP_201_CREATED,
        response_model=WarehouseCreateOut,
    )
    async def create_warehouse(
        payload: WarehouseCreateIn,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseCreateOut:
        check_perm(db, current_user, ["config.store.write"])

        sql = text(
            """
            INSERT INTO warehouses
              (name, code, active, address, contact_name, contact_phone, area_sqm)
            VALUES
              (:name, :code, :active, :address, :contact_name, :contact_phone, :area_sqm)
            RETURNING
              id, name, code, active, address, contact_name, contact_phone, area_sqm
            """
        )

        row = (
            (
                await session.execute(
                    sql,
                    {
                        "name": payload.name,
                        "code": payload.code,
                        "active": payload.active,
                        "address": payload.address,
                        "contact_name": payload.contact_name,
                        "contact_phone": payload.contact_phone,
                        "area_sqm": payload.area_sqm,
                    },
                )
            )
            .mappings()
            .first()
        )
        await session.commit()

        if not row:
            raise HTTPException(status_code=500, detail="failed to create warehouse")

        return WarehouseCreateOut(ok=True, data=row_to_warehouse(row))

    @router.patch("/warehouses/{warehouse_id}", response_model=WarehouseUpdateOut)
    async def update_warehouse(
        warehouse_id: int = Path(..., ge=1),
        payload: WarehouseUpdateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> WarehouseUpdateOut:
        check_perm(db, current_user, ["config.store.write"])

        fields: Dict[str, Any] = {}
        if payload.name is not None:
            fields["name"] = payload.name
        if payload.code is not None:
            fields["code"] = payload.code
        if payload.active is not None:
            fields["active"] = payload.active
        if payload.address is not None:
            fields["address"] = payload.address
        if payload.contact_name is not None:
            fields["contact_name"] = payload.contact_name
        if payload.contact_phone is not None:
            fields["contact_phone"] = payload.contact_phone
        if payload.area_sqm is not None:
            fields["area_sqm"] = payload.area_sqm

        if not fields:
            sql_select = text(
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
            row = (await session.execute(sql_select, {"wid": warehouse_id})).mappings().first()
            if not row:
                raise HTTPException(status_code=404, detail="warehouse not found")
            return WarehouseUpdateOut(ok=True, data=row_to_warehouse(row))

        set_clauses: list[str] = []
        params: Dict[str, Any] = {"wid": warehouse_id}
        for idx, (key, value) in enumerate(fields.items()):
            pname = f"v{idx}"
            set_clauses.append(f"{key} = :{pname}")
            params[pname] = value

        sql_update = text(
            f"""
            UPDATE warehouses
               SET {", ".join(set_clauses)}
             WHERE id = :wid
            RETURNING
              id, name, code, active, address, contact_name, contact_phone, area_sqm
            """
        )

        result = await session.execute(sql_update, params)
        row = result.mappings().first()
        await session.commit()

        if not row:
            raise HTTPException(status_code=404, detail="warehouse not found")

        return WarehouseUpdateOut(ok=True, data=row_to_warehouse(row))
