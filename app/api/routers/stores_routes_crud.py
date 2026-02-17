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

        ✅ 合同收敛：
        - shop_type 的唯一真相为 platform_test_shops（code='DEFAULT'）
        - 创建时可选择 TEST/PROD：
          * TEST：写入/更新 platform_test_shops（绑定 store_id）
          * PROD：确保该 store_id 不在 platform_test_shops（删除绑定）
        """
        from app.api.routers import stores as stores_router

        stores_router._check_perm(db, current_user, ["config.store.write"])

        platform = payload.platform.upper().strip()
        shop_id = str(payload.shop_id).strip()
        shop_type = str(payload.shop_type or "PROD").strip().upper()
        if shop_type not in ("TEST", "PROD"):
            raise HTTPException(status_code=400, detail=f"shop_type 非法：{shop_type}")

        store_id = await StoreService.ensure_store(
            session,
            platform=platform,
            shop_id=shop_id,
            name=payload.name,
        )

        # ✅ 根据 shop_type 写入/清理 platform_test_shops
        # 约束提醒：
        # - uq_platform_test_shops_platform_code：每个平台只有一个 code='DEFAULT'
        # - uq_platform_test_shops_store_id：store_id 只能绑定一次
        if shop_type == "TEST":
            # 1) 若该平台已存在 DEFAULT 测试店铺且不是当前 store_id，则报业务可解释错误
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id, store_id, shop_id
                          FROM platform_test_shops
                         WHERE platform = :plat
                           AND code = 'DEFAULT'
                         LIMIT 1
                        """
                    ),
                    {"plat": platform},
                )
            ).mappings().first()
            if row and row.get("store_id") is not None and int(row["store_id"]) != int(store_id):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"平台 {platform} 已存在默认测试店铺（code=DEFAULT），"
                        f"store_id={row.get('store_id')} shop_id={row.get('shop_id')}；"
                        f"不能再将 store_id={store_id} 设为 TEST。"
                    ),
                )

            # 2) 防御式清理：若当前 store_id 曾绑定在其他记录上，先解除（避免 uq_store_id 冲突）
            await session.execute(
                text(
                    """
                    UPDATE platform_test_shops
                       SET store_id = NULL
                     WHERE store_id = :sid
                       AND NOT (platform = :plat AND code = 'DEFAULT')
                    """
                ),
                {"sid": int(store_id), "plat": platform},
            )

            # 3) upsert DEFAULT：把平台/店铺锚点与 store_id 绑死
            await session.execute(
                text(
                    """
                    INSERT INTO platform_test_shops(platform, shop_id, store_id, code)
                    VALUES (:plat, :shop, :sid, 'DEFAULT')
                    ON CONFLICT (platform, code)
                    DO UPDATE SET
                      shop_id = EXCLUDED.shop_id,
                      store_id = EXCLUDED.store_id
                    """
                ),
                {"plat": platform, "shop": shop_id, "sid": int(store_id)},
            )

        else:
            # PROD：确保不在 DEFAULT 测试集合里
            await session.execute(
                text(
                    """
                    DELETE FROM platform_test_shops
                     WHERE store_id = :sid
                       AND code = 'DEFAULT'
                    """
                ),
                {"sid": int(store_id)},
            )

        await session.commit()

        return StoreCreateOut(
            ok=True,
            data={
                "store_id": store_id,
                "platform": platform,
                "shop_id": shop_id,
                "name": payload.name or f"{platform}-{shop_id}",
                "shop_type": shop_type,
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
