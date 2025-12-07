# app/api/routers/warehouses.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db
from app.services.user_service import AuthorizationError, UserService

router = APIRouter(tags=["warehouses"])


# ---------- Pydantic I/O ----------


class WarehouseOut(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    active: bool = True

    address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    area_sqm: Optional[int] = None


class WarehouseListOut(BaseModel):
    ok: bool = True
    data: List[WarehouseOut]


class WarehouseDetailOut(BaseModel):
    ok: bool = True
    data: WarehouseOut


class WarehouseCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=64)
    active: bool = True

    address: Optional[str] = Field(None, max_length=255)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=50)
    area_sqm: Optional[int] = Field(None, ge=0)


class WarehouseCreateOut(BaseModel):
    ok: bool = True
    data: WarehouseOut


class WarehouseUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=64)
    active: Optional[bool] = None

    address: Optional[str] = Field(None, max_length=255)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=50)
    area_sqm: Optional[int] = Field(None, ge=0)


class WarehouseUpdateOut(BaseModel):
    ok: bool = True
    data: WarehouseOut


# ---------- Helpers ----------


def _check_perm(db: Session, current_user, required: List[str]) -> None:
    """
    仓库模块权限检查入口。
    复用 stores 模块的 RBAC：config.store.read / config.store.write。
    """
    svc = UserService(db)
    try:
        svc.check_permission(current_user, required)
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized.")


def _row_to_warehouse(row: Any) -> WarehouseOut:
    return WarehouseOut(
        id=row["id"],
        name=row["name"],
        code=row.get("code"),
        active=row.get("active", True),
        address=row.get("address"),
        contact_name=row.get("contact_name"),
        contact_phone=row.get("contact_phone"),
        area_sqm=row.get("area_sqm"),
    )


# ---------- Routes ----------


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
    """
    仓库列表（用于前端列表、下拉等配置场景）。

    权限：config.store.read
    """
    _check_perm(db, current_user, ["config.store.read"])

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

    data = [_row_to_warehouse(row) for row in rows]
    return WarehouseListOut(ok=True, data=data)


@router.get(
    "/warehouses/{warehouse_id}",
    response_model=WarehouseDetailOut,
)
async def get_warehouse(
    warehouse_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseDetailOut:
    """
    仓库详情。

    权限：config.store.read
    """
    _check_perm(db, current_user, ["config.store.read"])

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

    return WarehouseDetailOut(ok=True, data=_row_to_warehouse(row))


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
    """
    新建仓库。

    权限：config.store.write
    """
    _check_perm(db, current_user, ["config.store.write"])

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

    return WarehouseCreateOut(ok=True, data=_row_to_warehouse(row))


@router.patch(
    "/warehouses/{warehouse_id}",
    response_model=WarehouseUpdateOut,
)
async def update_warehouse(
    warehouse_id: int = Path(..., ge=1),
    payload: WarehouseUpdateIn = ...,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> WarehouseUpdateOut:
    """
    更新仓库（name / code / active / address / contact_* / area_sqm）。

    权限：config.store.write
    """
    _check_perm(db, current_user, ["config.store.write"])

    # 整理要更新的字段
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

    # 如果没有字段要改，直接返回当前记录
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
        return WarehouseUpdateOut(ok=True, data=_row_to_warehouse(row))

    set_clauses: List[str] = []
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

    return WarehouseUpdateOut(ok=True, data=_row_to_warehouse(row))
