# app/api/routers/shipping_provider_pricing_schemes/schemas/surcharge.py
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_ALLOWED_SCOPE = {"province", "city"}


class SurchargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    name: str
    active: bool

    scope: str

    province_code: Optional[str] = None
    city_code: Optional[str] = None
    province_name: Optional[str] = None
    city_name: Optional[str] = None

    fixed_amount: Decimal


class SurchargeCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True

    scope: str = Field(..., min_length=1, max_length=16)

    province_code: Optional[str] = Field(None, max_length=32)
    city_code: Optional[str] = Field(None, max_length=32)
    province_name: Optional[str] = Field(None, max_length=64)
    city_name: Optional[str] = Field(None, max_length=64)

    fixed_amount: Decimal = Field(..., ge=0)

    @field_validator("scope")
    @classmethod
    def _scope_ok(cls, v: str) -> str:
        t = (v or "").strip().lower()
        if t not in _ALLOWED_SCOPE:
            raise ValueError("scope must be one of: province / city")
        return t

    @field_validator("province_code", "city_code", "province_name", "city_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        return t or None

    @model_validator(mode="after")
    def _validate_scope_and_amount(self):
        if self.scope == "province":
            if not (self.province_name or self.province_code):
                raise ValueError("province_name or province_code is required when scope=province")
            if self.city_name or self.city_code:
                raise ValueError("city_name/city_code must be empty when scope=province")

        if self.scope == "city":
            if not (self.province_name or self.province_code):
                raise ValueError("province_name or province_code is required when scope=city")
            if not (self.city_name or self.city_code):
                raise ValueError("city_name or city_code is required when scope=city")

        return self


class SurchargeUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    active: Optional[bool] = None

    scope: Optional[str] = Field(None, min_length=1, max_length=16)

    province_code: Optional[str] = Field(None, max_length=32)
    city_code: Optional[str] = Field(None, max_length=32)
    province_name: Optional[str] = Field(None, max_length=64)
    city_name: Optional[str] = Field(None, max_length=64)

    fixed_amount: Optional[Decimal] = Field(None, ge=0)

    @field_validator("scope")
    @classmethod
    def _scope_ok(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip().lower()
        if t not in _ALLOWED_SCOPE:
            raise ValueError("scope must be one of: province / city")
        return t

    @field_validator("province_code", "city_code", "province_name", "city_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        return t or None


class SurchargeUpsertIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scope: Literal["province", "city"]
    province_name: str = Field(..., min_length=1, max_length=64)
    city_name: Optional[str] = Field(None, min_length=1, max_length=64)

    province_code: Optional[str] = Field(None, max_length=32)
    city_code: Optional[str] = Field(None, max_length=32)

    name: Optional[str] = Field(None, min_length=1, max_length=128)

    amount: Decimal = Field(..., ge=0)
    active: bool = True

    @field_validator("province_name", "city_name", "province_code", "city_code")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        return t or None

    @model_validator(mode="after")
    def _validate_city(self):
        if self.scope == "city" and not self.city_name:
            raise ValueError("city_name is required when scope=city")
        if self.scope == "province" and (self.city_name or self.city_code):
            raise ValueError("city_name/city_code must be empty when scope=province")
        return self
