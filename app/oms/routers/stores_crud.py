# app/oms/routers/stores_crud.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.oms.contracts.stores import (
    StoreCreateIn,
    StoreCreateOut,
    StoreListItem,
    StoreListOut,
    StoreUpdateIn,
    StoreUpdateOut,
)
from app.oms.services.store_service import StoreService
from app.oms.services.stores_helpers import check_perm, ensure_store_exists


def register(router: APIRouter) -> None:
    @router.get("/stores", response_model=StoreListOut)
    async def list_stores(
        platform: str | None = Query(None, description="平台过滤（如 PDD/TB/DEMO），大小写不敏感"),
        q: str | None = Query(None, description="模糊搜索：store_name / store_code / id"),
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
        check_perm(db, current_user, ["config.store.read"])

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
                "s.store_name ILIKE :q_like "
                "OR s.store_code ILIKE :q_like "
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
              s.store_code,
              s.store_name,
              COALESCE(s.active, TRUE) AS active,
              COALESCE(s.route_mode, 'FALLBACK') AS route_mode,
              s.email,
              s.contact_name,
              s.contact_phone,
              CASE WHEN pts.id IS NULL THEN 'PROD' ELSE 'TEST' END AS store_type
            FROM stores AS s
            LEFT JOIN platform_test_stores AS pts
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
                store_code=row["store_code"],
                store_name=row["store_name"],
                active=row["active"],
                route_mode=row["route_mode"],
                store_type=row.get("store_type") or "PROD",
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
        - store_type 的唯一真相为 platform_test_stores（code='DEFAULT'）
        - 创建时可选择 TEST/PROD：
          * TEST：写入/更新 platform_test_stores（绑定 store_id）
          * PROD：确保该 store_id 不在 platform_test_stores（删除绑定）
        """
        check_perm(db, current_user, ["config.store.write"])

        platform = payload.platform.upper().strip()
        store_code = str(payload.store_code).strip()
        store_type = str(payload.store_type or "PROD").strip().upper()
        if store_type not in ("TEST", "PROD"):
            raise HTTPException(status_code=400, detail=f"store_type 非法：{store_type}")

        store_id = await StoreService.ensure_store(
            session,
            platform=platform,
            store_code=store_code,
            store_name=payload.store_name,
        )

        # ✅ 根据 store_type 写入/清理 platform_test_stores
        # 约束提醒：
        # - uq_platform_test_stores_platform_code：每个平台只有一个 code='DEFAULT'
        # - uq_platform_test_stores_store_id：store_id 只能绑定一次
        if store_type == "TEST":
            # 1) 若该平台已存在 DEFAULT 测试店铺且不是当前 store_id，则报业务可解释错误
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id, store_id, store_code
                          FROM platform_test_stores
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
                        f"store_id={row.get('store_id')} store_code={row.get('store_code')}；"
                        f"不能再将 store_id={store_id} 设为 TEST。"
                    ),
                )

            # 2) 防御式清理：若当前 store_id 曾绑定在其他记录上，先解除（避免 uq_store_id 冲突）
            await session.execute(
                text(
                    """
                    UPDATE platform_test_stores
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
                    INSERT INTO platform_test_stores(platform, store_code, store_id, code)
                    VALUES (:plat, :store, :sid, 'DEFAULT')
                    ON CONFLICT (platform, code)
                    DO UPDATE SET
                      store_code = EXCLUDED.store_code,
                      store_id = EXCLUDED.store_id
                    """
                ),
                {"plat": platform, "store": store_code, "sid": int(store_id)},
            )

        else:
            # platform_test_stores 仅用于测试店铺识别；商品集合隔离已退役
            await session.execute(
                text(
                    """
                    DELETE FROM platform_test_stores
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
                "store_code": store_code,
                "store_name": payload.store_name or f"{platform}-{store_code}",
                "store_type": store_type,
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
        check_perm(db, current_user, ["config.store.write"])

        await ensure_store_exists(session, store_id)

        fields: dict[str, Any] = {}
        if payload.store_name is not None:
            fields["store_name"] = payload.store_name
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
                  s.store_code,
                  s.store_name,
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
              store_code,
              store_name,
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
