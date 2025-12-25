# app/api/routers/stores_routes_bindings_read.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.stores_routes_bindings_helpers import check_store_perm, ensure_store_exists
from app.api.routers.stores_schemas import DefaultWarehouseOut, StoreDetailOut
from app.db.deps import get_db
from app.services.store_service import StoreService


def register(router: APIRouter) -> None:
    @router.get(
        "/stores/{store_id}/default-warehouse",
        response_model=DefaultWarehouseOut,
    )
    async def get_default_warehouse(
        store_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        解析默认仓（若无绑定返回 null）。
        权限：config.store.read
        """
        check_store_perm(db, current_user, ["config.store.read"])

        await ensure_store_exists(session, store_id)
        wid = await StoreService.resolve_default_warehouse(session, store_id=store_id)
        return DefaultWarehouseOut(ok=True, data={"warehouse_id": wid})

    @router.get("/stores/{store_id}", response_model=StoreDetailOut)
    async def get_store_detail(
        store_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        店铺详情（含绑定仓列表）。
        权限：config.store.read
        """
        check_store_perm(db, current_user, ["config.store.read"])

        sql = text(
            """
            SELECT
              s.platform,
              s.shop_id,
              s.name,
              s.email,
              s.contact_name,
              s.contact_phone,
              COALESCE(
                json_agg(
                  jsonb_build_object(
                    'warehouse_id',     sw.warehouse_id,
                    'warehouse_name',   w.name,
                    'warehouse_code',   w.code,
                    'warehouse_active', COALESCE(w.active, TRUE),
                    'is_top',           COALESCE(sw.is_top, FALSE),
                    'is_default',       COALESCE(sw.is_default, FALSE),
                    'priority',         COALESCE(sw.priority, 100)
                  )
                  ORDER BY sw.is_top DESC,
                           sw.is_default DESC,
                           sw.priority ASC,
                           sw.warehouse_id ASC
                ) FILTER (WHERE sw.warehouse_id IS NOT NULL),
                '[]'
              ) AS bindings
            FROM stores AS s
            LEFT JOIN store_warehouse AS sw
                   ON sw.store_id = s.id
            LEFT JOIN warehouses AS w
                   ON w.id = sw.warehouse_id
            WHERE s.id = :sid
            GROUP BY
              s.platform,
              s.shop_id,
              s.name,
              s.email,
              s.contact_name,
              s.contact_phone
            LIMIT 1
            """
        )
        row = (await session.execute(sql, {"sid": store_id})).first()
        if not row:
            raise HTTPException(status_code=404, detail="store not found")

        return StoreDetailOut(
            ok=True,
            data={
                "store_id": store_id,
                "platform": row[0],
                "shop_id": row[1],
                "name": row[2],
                "email": row[3],
                "contact_name": row[4],
                "contact_phone": row[5],
                "bindings": row[6],
            },
        )
