# app/api/routers/suppliers.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db
from app.services.user_service import AuthorizationError, UserService

router = APIRouter(tags=["suppliers"])


# ---------- Pydantic I/O ----------


class SupplierOut(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    wechat: Optional[str] = None
    active: bool = True


class SupplierListOut(BaseModel):
    ok: bool = True
    data: List[SupplierOut]


class SupplierDetailOut(BaseModel):
    ok: bool = True
    data: SupplierOut


class SupplierCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = Field(None, min_length=1, max_length=64)

    contact_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[str] = Field(None, max_length=64)

    active: bool = True


class SupplierCreateOut(BaseModel):
    ok: bool = True
    data: SupplierOut


class SupplierUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    code: Optional[str] = Field(None, min_length=1, max_length=64)

    contact_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[str] = Field(None, max_length=64)

    active: Optional[bool] = None


class SupplierUpdateOut(BaseModel):
    ok: bool = True
    data: SupplierOut


# ---------- Helpers ----------


def _check_perm(db: Session, current_user, required: List[str]) -> None:
    """
    供应商模块权限检查：
    复用 stores/warehouses 相同的 RBAC：config.store.read / config.store.write
    """
    svc = UserService(db)
    try:
        svc.check_permission(current_user, required)
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized.")


def _row_to_supplier(row: Any) -> SupplierOut:
    return SupplierOut(
        id=row["id"],
        name=row["name"],
        code=row.get("code"),
        contact_name=row.get("contact_name"),
        phone=row.get("phone"),
        email=row.get("email"),
        wechat=row.get("wechat"),
        active=row.get("active", True),
    )


# ---------- Routes ----------


@router.get("/suppliers", response_model=SupplierListOut)
async def list_suppliers(
    active: Optional[bool] = Query(
        None,
        description="按启用状态筛选；active=true 用于采购单下拉。",
    ),
    q: Optional[str] = Query(
        None,
        description="按名称 / 联系人模糊搜索。",
    ),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SupplierListOut:
    """
    供应商列表（用于前端列表、下拉等主数据配置场景）。

    权限：config.store.read
    """
    _check_perm(db, current_user, ["config.store.read"])

    where_clauses: List[str] = []
    params: Dict[str, Any] = {}

    if active is not None:
        where_clauses.append("s.active = :active")
        params["active"] = active

    if q:
        where_clauses.append("(s.name ILIKE :q OR s.contact_name ILIKE :q)")
        params["q"] = f"%{q.strip()}%"

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    sql = text(
        f"""
        SELECT
          s.id,
          s.name,
          s.code,
          s.contact_name,
          s.phone,
          s.email,
          s.wechat,
          s.active
        FROM suppliers AS s
        {where_sql}
        ORDER BY s.id
        """
    )

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    data = [_row_to_supplier(row) for row in rows]
    return SupplierListOut(ok=True, data=data)


@router.get(
    "/suppliers/{supplier_id}",
    response_model=SupplierDetailOut,
)
async def get_supplier(
    supplier_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SupplierDetailOut:
    """
    供应商详情。

    权限：config.store.read
    """
    _check_perm(db, current_user, ["config.store.read"])

    sql = text(
        """
        SELECT
          s.id,
          s.name,
          s.code,
          s.contact_name,
          s.phone,
          s.email,
          s.wechat,
          s.active
        FROM suppliers AS s
        WHERE s.id = :sid
        LIMIT 1
        """
    )

    row = (await session.execute(sql, {"sid": supplier_id})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="supplier not found")

    return SupplierDetailOut(ok=True, data=_row_to_supplier(row))


@router.post(
    "/suppliers",
    status_code=status.HTTP_201_CREATED,
    response_model=SupplierCreateOut,
)
async def create_supplier(
    payload: SupplierCreateIn,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SupplierCreateOut:
    """
    新建供应商。

    权限：config.store.write
    """
    _check_perm(db, current_user, ["config.store.write"])

    sql = text(
        """
        INSERT INTO suppliers
          (name, code, contact_name, phone, email, wechat, active)
        VALUES
          (:name, :code, :contact_name, :phone, :email, :wechat, :active)
        RETURNING
          id, name, code, contact_name, phone, email, wechat, active
        """
    )

    row = (
        (
            await session.execute(
                sql,
                {
                    "name": payload.name.strip(),
                    "code": payload.code.strip() if payload.code else None,
                    "contact_name": payload.contact_name,
                    "phone": payload.phone,
                    "email": payload.email,
                    "wechat": payload.wechat,
                    "active": payload.active,
                },
            )
        )
        .mappings()
        .first()
    )
    await session.commit()

    if not row:
        raise HTTPException(status_code=500, detail="failed to create supplier")

    return SupplierCreateOut(ok=True, data=_row_to_supplier(row))


@router.patch(
    "/suppliers/{supplier_id}",
    response_model=SupplierUpdateOut,
)
async def update_supplier(
    supplier_id: int = Path(..., ge=1),
    payload: SupplierUpdateIn = ...,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> SupplierUpdateOut:
    """
    更新供应商（name/code/contact/phone/email/wechat/active）。

    权限：config.store.write
    """
    _check_perm(db, current_user, ["config.store.write"])

    fields: Dict[str, Any] = {}
    if payload.name is not None:
        fields["name"] = payload.name.strip()
    if payload.code is not None:
        fields["code"] = payload.code.strip()
    if payload.contact_name is not None:
        fields["contact_name"] = payload.contact_name
    if payload.phone is not None:
        fields["phone"] = payload.phone
    if payload.email is not None:
        fields["email"] = payload.email
    if payload.wechat is not None:
        fields["wechat"] = payload.wechat
    if payload.active is not None:
        fields["active"] = payload.active

    # 没字段要改时，直接返回当前记录
    if not fields:
        sql_select = text(
            """
            SELECT
              s.id,
              s.name,
              s.code,
              s.contact_name,
              s.phone,
              s.email,
              s.wechat,
              s.active
            FROM suppliers AS s
            WHERE s.id = :sid
            LIMIT 1
            """
        )
        row = (await session.execute(sql_select, {"sid": supplier_id})).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="supplier not found")
        return SupplierUpdateOut(ok=True, data=_row_to_supplier(row))

    set_clauses: List[str] = []
    params: Dict[str, Any] = {"sid": supplier_id}
    for idx, (key, value) in enumerate(fields.items()):
        pname = f"v{idx}"
        set_clauses.append(f"{key} = :{pname}")
        params[pname] = value

    sql_update = text(
        f"""
        UPDATE suppliers
           SET {", ".join(set_clauses)},
               updated_at = now()
         WHERE id = :sid
        RETURNING
          id, name, code, contact_name, phone, email, wechat, active
        """
    )

    result = await session.execute(sql_update, params)
    row = result.mappings().first()
    await session.commit()

    if not row:
        raise HTTPException(status_code=404, detail="supplier not found")

    return SupplierUpdateOut(ok=True, data=_row_to_supplier(row))
