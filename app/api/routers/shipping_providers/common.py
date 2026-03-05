# app/api/routers/shipping_providers/common.py
from __future__ import annotations

from typing import Any, List, Optional

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
    """
    刚性契约（最新）：
    - 本对象语义为「运输网点实体」（保留表名 shipping_providers）
    - 与仓库为 M:N 关系，通过 warehouse_shipping_providers 表表达
    - code 为内部业务键（不可变）
    - external_outlet_code 为外部网点号（展示/对接用）
    """

    id: int
    name: str

    # 内部业务键（DB 级不可变 + 规范化 + NOT NULL）
    code: str

    # 外部网点号（展示/对接用，可空、可改）
    external_outlet_code: Optional[str] = Field(None, max_length=64)

    # 展示字段（不落库）
    display_label: str

    # ✅ 网点地址（可选）
    address: Optional[str] = Field(None, max_length=255)

    active: bool = True

    # 排序
    priority: int = 100

    # 联系人聚合（读）
    contacts: List[ShippingProviderContactOut] = Field(default_factory=list)


class ShippingProviderListOut(BaseModel):
    ok: bool = True
    data: List[ShippingProviderOut]


class ShippingProviderDetailOut(BaseModel):
    ok: bool = True
    data: ShippingProviderOut


class ShippingProviderCreateIn(BaseModel):
    """
    刚性契约（最新）：
    - code 必填（内部业务键，不可变）
    - external_outlet_code 可选（外部网点号，仅展示/对接）
    """

    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=64)

    external_outlet_code: Optional[str] = Field(None, min_length=1, max_length=64)

    # ✅ 网点地址（可选）
    address: Optional[str] = Field(None, max_length=255)

    active: bool = True

    # 排序
    priority: Optional[int] = Field(default=100, ge=0, description="排序优先级，数值越小优先级越高")


class ShippingProviderCreateOut(BaseModel):
    ok: bool = True
    data: ShippingProviderOut


class ShippingProviderUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)

    # 外部网点号（展示/对接用，可更新/可置空）
    external_outlet_code: Optional[str] = Field(None, min_length=1, max_length=64)

    # ✅ 网点地址（可更新/可置空）
    address: Optional[str] = Field(None, max_length=255)

    active: Optional[bool] = None

    # 排序
    priority: Optional[int] = Field(default=None, ge=0)


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
    ext = row.get("external_outlet_code")
    name = row["name"]
    display = f"{name}（{ext}）" if ext else name

    return ShippingProviderOut(
        id=row["id"],
        name=name,
        code=row["code"],
        external_outlet_code=ext,
        display_label=display,
        address=row.get("address"),
        active=row.get("active", True),
        priority=row.get("priority", 100),
        contacts=contacts,
    )
