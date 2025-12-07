from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, constr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db
from app.services.store_service import StoreService
from app.services.user_service import AuthorizationError, UserService

router = APIRouter(tags=["stores"])

# ---------- Pydantic I/O ----------

PlatformStr = constr(min_length=2, max_length=32)


class StoreCreateIn(BaseModel):
    platform: PlatformStr
    shop_id: constr(min_length=1, max_length=128)
    name: Optional[constr(min_length=1, max_length=256)] = None
    # 创建时是否允许传 email/联系人/电话，看你需求，这里先不暴露：
    # email: Optional[constr(max_length=255)] = None
    # contact_name: Optional[constr(max_length=100)] = None
    # contact_phone: Optional[constr(max_length=50)] = None


class StoreCreateOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class BindWarehouseIn(BaseModel):
    warehouse_id: int = Field(..., ge=1)
    is_default: bool = False
    priority: int = Field(100, ge=0, le=100_000)
    # 若不传 is_top，由后端按 is_default 推导
    is_top: Optional[bool] = Field(
        default=None,
        description="是否主仓；若为 null，由后端按 is_default 推导",
    )


class BindWarehouseOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class DefaultWarehouseOut(BaseModel):
    ok: bool = True
    data: Dict[str, Optional[int]]


class StoreDetailOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class StoreListItem(BaseModel):
    id: int
    platform: str
    shop_id: str
    name: str
    active: bool
    route_mode: str

    # 新增主数据字段
    email: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None


class StoreListOut(BaseModel):
    ok: bool = True
    data: List[StoreListItem]


class StoreUpdateIn(BaseModel):
    name: Optional[constr(min_length=1, max_length=256)] = None
    active: Optional[bool] = None
    route_mode: Optional[constr(min_length=1, max_length=32)] = None

    # 新增：可更新 email / 联系人 / 电话
    email: Optional[constr(max_length=255)] = None
    contact_name: Optional[constr(max_length=100)] = None
    contact_phone: Optional[constr(max_length=50)] = None


class StoreUpdateOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class BindingUpdateIn(BaseModel):
    is_default: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0, le=100_000)
    is_top: Optional[bool] = None


class BindingUpdateOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class BindingDeleteOut(BaseModel):
    ok: bool = True
    data: Dict[str, Any]


class StorePlatformAuthOut(BaseModel):
    """
    店铺平台授权状态返回：

    data:
      - store_id
      - platform
      - shop_id
      - auth_source: "NONE" / "MANUAL" / "OAUTH"
      - expires_at: ISO 字符串或 null
      - mall_id: 平台侧店铺 ID（如 PDD mall_id），可能为 null
    """

    ok: bool = True
    data: Dict[str, Any]


# ---------- Helpers ----------


async def _ensure_store_exists(session: AsyncSession, store_id: int) -> None:
    row = await session.execute(
        text(
            """
            SELECT 1
              FROM stores
             WHERE id = :sid
             LIMIT 1
            """
        ),
        {"sid": store_id},
    )
    if row.first() is None:
        raise HTTPException(status_code=404, detail="store not found")


async def _ensure_warehouse_exists(
    session: AsyncSession,
    warehouse_id: int,
    *,
    require_active: bool = False,
) -> None:
    """
    校验仓库存在；若 require_active=True，则同时要求 active=TRUE。
    """
    row = await session.execute(
        text(
            """
            SELECT active
              FROM warehouses
             WHERE id = :wid
             LIMIT 1
            """
        ),
        {"wid": warehouse_id},
    )
    rec = row.mappings().first()
    if rec is None:
        raise HTTPException(status_code=404, detail="warehouse not found")

    if require_active and not rec.get("active", True):
        raise HTTPException(status_code=400, detail="warehouse is inactive")


def _check_perm(
    db: Session,
    current_user,
    required: list[str],
):
    """
    统一的 store 配置权限检查入口。
    """
    svc = UserService(db)
    try:
        svc.check_permission(current_user, required)
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized.")


# ---------- Routes ----------


@router.get("/stores", response_model=StoreListOut)
async def list_stores(
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    店铺列表（基础信息，不含仓绑定）。

    权限：config.store.read
    """
    _check_perm(db, current_user, ["config.store.read"])

    sql = text(
        """
        SELECT
          s.id,
          s.platform,
          s.shop_id,
          s.name,
          COALESCE(s.active, TRUE) AS active,
          COALESCE(s.route_mode, 'FALLBACK') AS route_mode,
          s.email,
          s.contact_name,
          s.contact_phone
        FROM stores AS s
        ORDER BY s.id
        """
    )

    result = await session.execute(sql)
    rows = result.mappings().all()

    items = [
        StoreListItem(
            id=row["id"],
            platform=row["platform"],
            shop_id=row["shop_id"],
            name=row["name"],
            active=row["active"],
            route_mode=row["route_mode"],
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
    _check_perm(db, current_user, ["config.store.write"])

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
    _check_perm(db, current_user, ["config.store.write"])

    await _ensure_store_exists(session, store_id)

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


# 下面绑定相关路由 / 默认仓 / 详情 / 平台授权，除了详情要多带几个字段，其它不动


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
    _check_perm(db, current_user, ["config.store.write"])

    await _ensure_store_exists(session, store_id)
    # 绑定时必须是 active 仓库
    await _ensure_warehouse_exists(
        session,
        payload.warehouse_id,
        require_active=True,
    )

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
    _check_perm(db, current_user, ["config.store.write"])

    await _ensure_store_exists(session, store_id)
    await _ensure_warehouse_exists(session, warehouse_id)

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
    _check_perm(db, current_user, ["config.store.write"])

    await _ensure_store_exists(session, store_id)
    await _ensure_warehouse_exists(session, warehouse_id)

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
    _check_perm(db, current_user, ["config.store.read"])

    await _ensure_store_exists(session, store_id)
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
    _check_perm(db, current_user, ["config.store.read"])

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


@router.get(
    "/stores/{store_id}/platform-auth",
    response_model=StorePlatformAuthOut,
)
async def get_store_platform_auth(
    store_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    店铺平台授权状态视图：

    data:
      - store_id
      - platform
      - shop_id
      - auth_source: "NONE" / "MANUAL" / "OAUTH"
      - expires_at
      - mall_id
    """
    _check_perm(db, current_user, ["config.store.read"])

    # 1) 查 store 平台与 shop_id
    sql_store = text(
        """
        SELECT platform, shop_id
          FROM stores
         WHERE id = :sid
         LIMIT 1
        """
    )
    row = (await session.execute(sql_store, {"sid": store_id})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="store not found")

    platform = (row["platform"] or "").upper()
    shop_id = row["shop_id"]

    # 2) 查 store_tokens（按 store_id + platform 小写）
    sql_token = text(
        """
        SELECT mall_id, expires_at, refresh_token
          FROM store_tokens
         WHERE store_id = :sid
           AND platform = :plat
         ORDER BY id DESC
         LIMIT 1
        """
    )
    row_token = (
        (
            await session.execute(
                sql_token,
                {"sid": store_id, "plat": platform.lower()},
            )
        )
        .mappings()
        .first()
    )

    if not row_token:
        return StorePlatformAuthOut(
            ok=True,
            data={
                "store_id": store_id,
                "platform": platform,
                "shop_id": shop_id,
                "auth_source": "NONE",
                "expires_at": None,
                "mall_id": None,
            },
        )

    refresh_token = row_token["refresh_token"] or ""
    auth_source = "MANUAL" if refresh_token == "MANUAL" else "OAUTH"

    return StorePlatformAuthOut(
        ok=True,
        data={
            "store_id": store_id,
            "platform": platform,
            "shop_id": shop_id,
            "auth_source": auth_source,
            "expires_at": row_token["expires_at"].isoformat() if row_token["expires_at"] else None,
            "mall_id": row_token["mall_id"],
        },
    )
