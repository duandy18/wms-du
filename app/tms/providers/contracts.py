# app/tms/providers/contracts.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


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


class ShippingProviderOut(BaseModel):
    """
    刚性契约（最新）：
    - 本对象语义为「运输网点实体」（保留表名 shipping_providers）
    - 与仓库为 M:N 关系，通过 warehouse_shipping_providers 表表达
    - code 为内部业务键（允许修改，但保持唯一与规范化）
    - company_code / resource_code 为电子面单固定接入参数
    """

    id: int
    name: str
    code: str
    display_label: str
    company_code: Optional[str] = Field(None, max_length=64)
    resource_code: Optional[str] = Field(None, max_length=64)
    address: Optional[str] = Field(None, max_length=255)
    active: bool = True
    priority: int = 100
    contacts: List[ShippingProviderContactOut] = Field(default_factory=list)


class ShippingProviderListOut(BaseModel):
    ok: bool = True
    data: List[ShippingProviderOut]


class ShippingProviderDetailOut(BaseModel):
    ok: bool = True
    data: ShippingProviderOut


class ShippingProviderCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=64)
    company_code: Optional[str] = Field(None, max_length=64)
    resource_code: Optional[str] = Field(None, max_length=64)
    address: Optional[str] = Field(None, max_length=255)
    active: bool = True
    priority: Optional[int] = Field(default=100, ge=0, description="排序优先级，数值越小优先级越高")


class ShippingProviderCreateOut(BaseModel):
    ok: bool = True
    data: ShippingProviderOut


class ShippingProviderUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    code: Optional[str] = Field(None, min_length=1, max_length=64)
    company_code: Optional[str] = Field(None, max_length=64)
    resource_code: Optional[str] = Field(None, max_length=64)
    address: Optional[str] = Field(None, max_length=255)
    active: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=0)


class ShippingProviderUpdateOut(BaseModel):
    ok: bool = True
    data: ShippingProviderOut


class ShippingProviderContactCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[str] = Field(None, max_length=64)
    role: str = Field(default="other", max_length=32)
    is_primary: bool = False
    active: bool = True


class ShippingProviderContactUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=255)
    wechat: Optional[EmailStr] | Optional[str] = Field(None, max_length=64)
    role: Optional[str] = Field(None, max_length=32)
    is_primary: Optional[bool] = None
    active: Optional[bool] = None
