# app/api/routers/shipping_providers.py
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

router = APIRouter(tags=["shipping-providers"])


class ShippingProviderOut(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    wechat: Optional[str] = None
    active: bool = True

    # 费率相关
    priority: int = 100
    pricing_model: Optional[Dict[str, Any]] = None
    region_rules: Optional[Dict[str, Any]] = None


class ShippingProviderListOut(BaseModel):
    ok: bool = True
    data: List[ShippingProviderOut]


class ShippingProviderDetailOut(BaseModel):
    ok: bool = True
    data: ShippingProviderOut


class ShippingProviderCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = Field(None, min_length=1, max_length=64)

    contact_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[str] = Field(None, max_length=64)

    active: bool = True

    # 费率相关（可选）
    priority: Optional[int] = Field(default=100, ge=0, description="排序优先级，数值越小优先级越高")
    pricing_model: Optional[Dict[str, Any]] = Field(
        default=None,
        description="计费模型 JSON，例如 {type: 'by_weight', base_weight: 1, base_cost: 3.5, extra_unit: 1, extra_cost: 1.2}",
    )
    region_rules: Optional[Dict[str, Any]] = Field(
        default=None,
        description="区域覆盖规则 JSON，例如 {'广东省': {base_cost: 3.2}}",
    )


class ShippingProviderCreateOut(BaseModel):
    ok: bool = True
    data: ShippingProviderOut


class ShippingProviderUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    code: Optional[str] = Field(None, min_length=1, max_length=64)

    contact_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[str] = Field(None, max_length=64)

    active: Optional[bool] = None

    # 费率相关
    priority: Optional[int] = Field(default=None, ge=0)
    pricing_model: Optional[Dict[str, Any]] = None
    region_rules: Optional[Dict[str, Any]] = None


class ShippingProviderUpdateOut(BaseModel):
    ok: bool = True
    data: ShippingProviderOut


def _check_perm(db: Session, current_user, required: List[str]) -> None:
    svc = UserService(db)
    try:
        svc.check_permission(current_user, required)
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized.")


def _row_to_provider(row: Any) -> ShippingProviderOut:
    return ShippingProviderOut(
        id=row["id"],
        name=row["name"],
        code=row.get("code"),
        contact_name=row.get("contact_name"),
        phone=row.get("phone"),
        email=row.get("email"),
        wechat=row.get("wechat"),
        active=row.get("active", True),
        priority=row.get("priority", 100),
        pricing_model=row.get("pricing_model"),
        region_rules=row.get("region_rules"),
    )


@router.get("/shipping-providers", response_model=ShippingProviderListOut)
async def list_shipping_providers(
    active: Optional[bool] = Query(
        None,
        description="按启用状态筛选；active=true 用于下拉。",
    ),
    q: Optional[str] = Query(
        None,
        description="按名称 / 联系人模糊搜索。",
    ),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ShippingProviderListOut:
    """
    物流/快递公司列表。

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
          s.active,
          s.priority,
          s.pricing_model,
          s.region_rules
        FROM shipping_providers AS s
        {where_sql}
        ORDER BY s.priority ASC, s.id ASC
        """
    )

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    data = [_row_to_provider(row) for row in rows]
    return ShippingProviderListOut(ok=True, data=data)


@router.get(
    "/shipping-providers/{provider_id}",
    response_model=ShippingProviderDetailOut,
)
async def get_shipping_provider(
    provider_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ShippingProviderDetailOut:
    """
    物流/快递公司详情。

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
          s.active,
          s.priority,
          s.pricing_model,
          s.region_rules
        FROM shipping_providers AS s
        WHERE s.id = :sid
        LIMIT 1
        """
    )

    row = (await session.execute(sql, {"sid": provider_id})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="shipping_provider not found")

    return ShippingProviderDetailOut(ok=True, data=_row_to_provider(row))


@router.post(
    "/shipping-providers",
    status_code=status.HTTP_201_CREATED,
    response_model=ShippingProviderCreateOut,
)
async def create_shipping_provider(
    payload: ShippingProviderCreateIn,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ShippingProviderCreateOut:
    """
    新建物流/快递公司。

    权限：config.store.write
    """
    _check_perm(db, current_user, ["config.store.write"])

    sql = text(
        """
        INSERT INTO shipping_providers
          (name, code, contact_name, phone, email, wechat, active, priority, pricing_model, region_rules)
        VALUES
          (:name, :code, :contact_name, :phone, :email, :wechat, :active, :priority, :pricing_model, :region_rules)
        RETURNING
          id, name, code, contact_name, phone, email, wechat, active, priority, pricing_model, region_rules
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
                    "priority": payload.priority if payload.priority is not None else 100,
                    "pricing_model": payload.pricing_model,
                    "region_rules": payload.region_rules,
                },
            )
        )
        .mappings()
        .first()
    )
    await session.commit()

    if not row:
        raise HTTPException(
            status_code=500,
            detail="failed to create shipping provider",
        )

    return ShippingProviderCreateOut(ok=True, data=_row_to_provider(row))


@router.patch(
    "/shipping-providers/{provider_id}",
    response_model=ShippingProviderUpdateOut,
)
async def update_shipping_provider(
    provider_id: int = Path(..., ge=1),
    payload: ShippingProviderUpdateIn = ...,
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ShippingProviderUpdateOut:
    """
    更新物流/快递公司。

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
    if payload.priority is not None:
        fields["priority"] = payload.priority
    if payload.pricing_model is not None:
        fields["pricing_model"] = payload.pricing_model
    if payload.region_rules is not None:
        fields["region_rules"] = payload.region_rules

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
              s.active,
              s.priority,
              s.pricing_model,
              s.region_rules
            FROM shipping_providers AS s
            WHERE s.id = :sid
            LIMIT 1
            """
        )
        row = (await session.execute(sql_select, {"sid": provider_id})).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="shipping_provider not found")
        return ShippingProviderUpdateOut(ok=True, data=_row_to_provider(row))

    set_clauses: List[str] = []
    params: Dict[str, Any] = {"sid": provider_id}
    for idx, (key, value) in enumerate(fields.items()):
        pname = f"v{idx}"
        set_clauses.append(f"{key} = :{pname}")
        params[pname] = value

    sql_update = text(
        f"""
        UPDATE shipping_providers
           SET {", ".join(set_clauses)},
               updated_at = now()
         WHERE id = :sid
        RETURNING
          id, name, code, contact_name, phone, email, wechat, active, priority, pricing_model, region_rules
        """
    )

    result = await session.execute(sql_update, params)
    row = result.mappings().first()
    await session.commit()

    if not row:
        raise HTTPException(status_code=404, detail="shipping_provider not found")

    return ShippingProviderUpdateOut(ok=True, data=_row_to_provider(row))
