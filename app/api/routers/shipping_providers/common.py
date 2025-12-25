# app/api/routers/shipping_providers/common.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.services.user_service import AuthorizationError, UserService


# -----------------------
# Contacts Schemas
# -----------------------


class ShippingProviderContactOut(BaseModel):
    id: int
    shipping_provider_id: int
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    wechat: Optional[str] = None
    role: str
    is_primary: bool
    active: bool


# -----------------------
# Provider Schemas
# -----------------------


class ShippingProviderOut(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    active: bool = True

    # 费率相关
    priority: int = 100
    pricing_model: Optional[Dict[str, Any]] = None
    region_rules: Optional[Dict[str, Any]] = None

    # 联系人聚合（读）
    contacts: List[ShippingProviderContactOut] = Field(default_factory=list)


class ShippingProviderListOut(BaseModel):
    ok: bool = True
    data: List[ShippingProviderOut]


class ShippingProviderDetailOut(BaseModel):
    ok: bool = True
    data: ShippingProviderOut


class ShippingProviderCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: Optional[str] = Field(None, min_length=1, max_length=64)
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


def _row_to_contact(row: Any) -> ShippingProviderContactOut:
    return ShippingProviderContactOut(
        id=row["id"],
        shipping_provider_id=row["shipping_provider_id"],
        name=row["name"],
        phone=row.get("phone"),
        email=row.get("email"),
        wechat=row.get("wechat"),
        role=row.get("role") or "other",
        is_primary=bool(row.get("is_primary", False)),
        active=bool(row.get("active", True)),
    )


def _row_to_provider(row: Any, contacts: List[ShippingProviderContactOut]) -> ShippingProviderOut:
    return ShippingProviderOut(
        id=row["id"],
        name=row["name"],
        code=row.get("code"),
        active=row.get("active", True),
        priority=row.get("priority", 100),
        pricing_model=row.get("pricing_model"),
        region_rules=row.get("region_rules"),
        contacts=contacts,
    )
