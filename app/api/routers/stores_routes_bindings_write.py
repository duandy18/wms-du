# app/api/routers/stores_routes_bindings_write.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.stores_routes_bindings_helpers import (
    check_store_perm,
    ensure_store_exists,
    ensure_warehouse_exists,
)
from app.api.routers.stores_schemas import (
    BindWarehouseIn,
    BindWarehouseOut,
    BindingDeleteOut,
    BindingUpdateIn,
    BindingUpdateOut,
)
from app.db.deps import get_db
from app.services.store_service import StoreService


def register(router: APIRouter) -> None:
    @router.post(
        "/stores/{store_id}/warehouses/bind",
        response_model=BindWarehouseOut,
    )
    async def bind_store_warehouse(
        store_id: int = Path(..., ge=1),
        payload: BindWarehouseIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        店 ↔ 仓 绑定（幂等）。
        权限：config.store.write
        """
        check_store_perm(db, current_user, ["config.store.write"])

        await ensure_store_exists(session, store_id)
        await ensure_warehouse_exists(session, payload.warehouse_id, require_active=True)

        await StoreService.bind_warehouse(
            session,
            store_id=store_id,
            warehouse_id=payload.warehouse_id,
            is_default=payload.is_default,
            priority=payload.priority,
            is_top=payload.is_top,
        )
        await session.commit()

        return BindWarehouseOut(
            ok=True,
            data={
                "store_id": store_id,
                "warehouse_id": payload.warehouse_id,
                "is_default": payload.is_default,
                "is_top": payload.is_top if payload.is_top is not None else payload.is_default,
                "priority": payload.priority,
            },
        )

    @router.patch(
        "/stores/{store_id}/warehouses/{warehouse_id}",
        response_model=BindingUpdateOut,
    )
    async def update_binding(
        store_id: int = Path(..., ge=1),
        warehouse_id: int = Path(..., ge=1),
        payload: BindingUpdateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        更新绑定关系（is_default / priority / is_top）。
        权限：config.store.write
        """
        check_store_perm(db, current_user, ["config.store.write"])

        await ensure_store_exists(session, store_id)
        await ensure_warehouse_exists(session, warehouse_id)

        fields: dict[str, Any] = {}
        if payload.is_default is not None:
            fields["is_default"] = payload.is_default
        if payload.priority is not None:
            fields["priority"] = payload.priority
        if payload.is_top is not None:
            fields["is_top"] = payload.is_top

        if not fields:
            raise HTTPException(status_code=400, detail="no fields to update")

        set_clauses: list[str] = []
        params: dict[str, Any] = {"sid": store_id, "wid": warehouse_id}
        for idx, (key, value) in enumerate(fields.items()):
            param = f"{key}_{idx}"
            set_clauses.append(f"{key} = :{param}")
            params[param] = value

        sql = text(
            f"""
            UPDATE store_warehouse
               SET {", ".join(set_clauses)},
                   updated_at = now()
             WHERE store_id = :sid
               AND warehouse_id = :wid
            RETURNING store_id, warehouse_id, is_default, is_top, priority
            """
        )
        result = await session.execute(sql, params)
        row = result.mappings().first()
        await session.commit()

        if not row:
            raise HTTPException(status_code=404, detail="binding not found")

        return BindingUpdateOut(ok=True, data=row)

    @router.delete(
        "/stores/{store_id}/warehouses/{warehouse_id}",
        response_model=BindingDeleteOut,
    )
    async def delete_binding(
        store_id: int = Path(..., ge=1),
        warehouse_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        解除店 ↔ 仓 绑定关系。
        权限：config.store.write
        """
        check_store_perm(db, current_user, ["config.store.write"])

        await ensure_store_exists(session, store_id)
        await ensure_warehouse_exists(session, warehouse_id)

        sql = text(
            """
            DELETE FROM store_warehouse
             WHERE store_id = :sid
               AND warehouse_id = :wid
            RETURNING id
            """
        )
        result = await session.execute(sql, {"sid": store_id, "wid": warehouse_id})
        row = result.first()
        await session.commit()

        if not row:
            raise HTTPException(status_code=404, detail="binding not found")

        return BindingDeleteOut(ok=True, data={"store_id": store_id, "warehouse_id": warehouse_id})
