# app/api/routers/stores_routes_crud.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db
from app.api.routers.stores_schemas import (
    StoreCreateIn,
    StoreCreateOut,
    StoreListItem,
    StoreListOut,
    StoreUpdateIn,
    StoreUpdateOut,
)
from app.services.store_service import StoreService


def register(router: APIRouter) -> None:
    @router.get("/stores", response_model=StoreListOut)
    async def list_stores(
        platform: str | None = Query(None, description="平台过滤（如 PDD/TB/DEMO），大小写不敏感"),
        q: str | None = Query(None, description="模糊搜索：name / shop_id / id"),
        limit: int = Query(200, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        店铺列表（基础信息，不含仓绑定）。

        权限：config.store.read

        ✅ 合同：
        - 支持 platform/q/limit/offset
        - 返回结构保持：{ ok: true, data: [...] }
        """
        # ✅ 运行时从 stores 模块取 _check_perm，保证测试 monkeypatch 生效
        from app.api.routers import stores as stores_router

        stores_router._check_perm(db, current_user, ["config.store.read"])

        where_parts: list[str] = ["1=1"]
        params: dict[str, Any] = {}

        plat = (platform or "").strip()
        if plat:
            where_parts.append("upper(s.platform) = :platform")
            params["platform"] = plat.upper()

        kw = (q or "").strip()
        if kw:
            where_parts.append(
                "("
                "s.name ILIKE :q_like "
                "OR s.shop_id ILIKE :q_like "
                "OR CAST(s.id AS TEXT) ILIKE :q_like"
                ")"
            )
            params["q_like"] = f"%{kw}%"

        params["limit"] = int(limit)
        params["offset"] = int(offset)

        sql = text(
            f"""
            SELECT
              s.id,
              s.platform,
              s.shop_id,
              s.name,
              COALESCE(s.active, TRUE) AS active,
              COALESCE(s.route_mode, 'FALLBACK') AS route_mode,
              s.email,
              s.contact_name,
              s.contact_phone,
              CASE WHEN pts.id IS NULL THEN 'PROD' ELSE 'TEST' END AS shop_type
            FROM stores AS s
            LEFT JOIN platform_test_shops AS pts
              ON pts.store_id = s.id
             AND pts.code = 'DEFAULT'
            WHERE {' AND '.join(where_parts)}
            ORDER BY s.id
            LIMIT :limit OFFSET :offset
            """
        )

        result = await session.execute(sql, params)
        rows = result.mappings().all()

        items = [
            StoreListItem(
                id=row["id"],
                platform=row["platform"],
                shop_id=row["shop_id"],
                name=row["name"],
                active=row["active"],
                route_mode=row["route_mode"],
                shop_type=row.get("shop_type") or "PROD",
                email=row.get("email"),
                contact_name=row.get("contact_name"),
                contact_phone=row.get("contact_phone"),
            )
            for row in rows
        ]

        return StoreListOut(ok=True, data=items)

    @router.post("/stores", response_model=StoreCreateOut)
    async def create_or_get_store(
        payload: StoreCreateIn,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        店铺建档 / 补录（幂等）。

        权限：config.store.write
        """
        from app.api.routers import stores as stores_router

        stores_router._check_perm(db, current_user, ["config.store.write"])

        platform = payload.platform.upper()
        store_id = await StoreService.ensure_store(
            session,
            platform=platform,
            shop_id=payload.shop_id,
            name=payload.name,
        )
        await session.commit()

        return StoreCreateOut(
            ok=True,
            data={
                "store_id": store_id,
                "platform": platform,
                "shop_id": payload.shop_id,
                "name": payload.name or f"{platform}-{payload.shop_id}",
                # email / contact_* 可以以后再扩充返回
            },
        )

    @router.patch("/stores/{store_id}", response_model=StoreUpdateOut)
    async def update_store(
        store_id: int = Path(..., ge=1),
        payload: StoreUpdateIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        更新店铺基础信息（name / active / route_mode / email / 联系人 / 电话）。

        权限：config.store.write
        """
        from app.api.routers import stores as stores_router

        stores_router._check_perm(db, current_user, ["config.store.write"])

        await stores_router._ensure_store_exists(session, store_id)

        fields: dict[str, Any] = {}
        if payload.name is not None:
            fields["name"] = payload.name
        if payload.active is not None:
            fields["active"] = payload.active
        if payload.route_mode is not None:
            fields["route_mode"] = payload.route_mode
        if payload.email is not None:
            fields["email"] = payload.email
        if payload.contact_name is not None:
            fields["contact_name"] = payload.contact_name
        if payload.contact_phone is not None:
            fields["contact_phone"] = payload.contact_phone

        if not fields:
            sql_select = text(
                """
                SELECT
                  s.id,
                  s.platform,
                  s.shop_id,
                  s.name,
                  s.active,
                  s.route_mode,
                  s.email,
                  s.contact_name,
                  s.contact_phone
                FROM stores AS s
                WHERE s.id = :sid
                LIMIT 1
                """
            )
            row = (await session.execute(sql_select, {"sid": store_id})).first()
            if not row:
                raise HTTPException(status_code=404, detail="store not found")
            return StoreUpdateOut(ok=True, data=dict(row))

        set_clauses: list[str] = []
        params: dict[str, Any] = {"sid": store_id}
        for idx, (key, value) in enumerate(fields.items()):
            param = f"v{idx}"
            set_clauses.append(f"{key} = :{param}")
            params[param] = value

        sql_update = text(
            f"""
            UPDATE stores
               SET {", ".join(set_clauses)},
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = :sid
            RETURNING
              id,
              platform,
              shop_id,
              name,
              active,
              route_mode,
              email,
              contact_name,
              contact_phone
            """
        )
        result = await session.execute(sql_update, params)
        row = result.mappings().first()
        await session.commit()

        if not row:
            raise HTTPException(status_code=404, detail="store not found")

        return StoreUpdateOut(ok=True, data=row)
