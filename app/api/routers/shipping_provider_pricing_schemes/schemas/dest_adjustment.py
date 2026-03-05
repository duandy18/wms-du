# app/api/routers/shipping_provider_pricing_schemes/schemas/dest_adjustment.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DestAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    scope: str

    # ✅ 新：code 事实（最终口径）
    province_code: str
    city_code: Optional[str] = None

    # ✅ 新：展示冗余
    province_name: Optional[str] = None
    city_name: Optional[str] = None

    # ✅ 兼容旧字段（输出用，后续可退场）
    province: str
    city: Optional[str] = None

    amount: float
    active: bool
    priority: int
    created_at: datetime
    updated_at: datetime


class DestAdjustmentUpsertIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scope: str = Field(..., description="province|city")

    # ✅ 只收 code
    province_code: str
    city_code: Optional[str] = None

    # ✅ 可选展示冗余（可传可不传；后端会按字典补全/校验）
    province_name: Optional[str] = None
    city_name: Optional[str] = None

    amount: float
    active: bool = True
    priority: int = 100

    @field_validator("scope")
    @classmethod
    def _scope(cls, v: str) -> str:
        v2 = (v or "").strip().lower()
        if v2 not in ("province", "city"):
            raise ValueError("scope must be 'province' or 'city'")
        return v2

    @field_validator("province_code", "city_code", "province_name", "city_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip()
        return v2 or None

    @field_validator("amount")
    @classmethod
    def _amount(cls, v: float) -> float:
        if v < 0:
            raise ValueError("amount must be >= 0")
        return v

    @model_validator(mode="after")
    def _scope_city_rules(self):
        if self.scope == "province":
            # province scope：city_code 必须为空
            if self.city_code:
                raise ValueError("city_code must be null when scope='province'")
        if self.scope == "city":
            # city scope：city_code 必填
            if not self.city_code:
                raise ValueError("city_code is required when scope='city'")
        return self


class DestAdjustmentUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scope: Optional[str] = None

    # ✅ 只收 code（可选）
    province_code: Optional[str] = None
    city_code: Optional[str] = None

    # ✅ 可选展示冗余
    province_name: Optional[str] = None
    city_name: Optional[str] = None

    amount: Optional[float] = None
    active: Optional[bool] = None
    priority: Optional[int] = None

    @field_validator("scope")
    @classmethod
    def _scope(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip().lower()
        if v2 not in ("province", "city"):
            raise ValueError("scope must be 'province' or 'city'")
        return v2

    @field_validator("province_code", "city_code", "province_name", "city_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip()
        return v2 or None

    @field_validator("amount")
    @classmethod
    def _amount(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if v < 0:
            raise ValueError("amount must be >= 0")
        return v
