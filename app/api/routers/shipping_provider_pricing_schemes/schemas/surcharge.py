# app/api/routers/shipping_provider_pricing_schemes/schemas/surcharge.py
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_ALLOWED_PROVINCE_MODE = {"province", "cities"}


def _trim_or_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    t = v.strip()
    return t or None


class SurchargeConfigCityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    config_id: int
    city_code: str
    city_name: Optional[str] = None
    fixed_amount: Decimal
    active: bool


class SurchargeConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    province_code: str
    province_name: Optional[str] = None
    province_mode: Literal["province", "cities"]
    fixed_amount: Decimal
    active: bool
    cities: list[SurchargeConfigCityOut] = Field(default_factory=list)


class SurchargeConfigCityIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    city_code: str = Field(..., min_length=1, max_length=32)
    city_name: Optional[str] = Field(None, max_length=64)
    fixed_amount: Decimal = Field(..., ge=0)
    active: bool = True

    @field_validator("city_code", "city_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        return _trim_or_none(v)


class SurchargeConfigCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    province_code: str = Field(..., min_length=1, max_length=32)
    province_name: Optional[str] = Field(None, max_length=64)

    province_mode: Literal["province", "cities"]

    fixed_amount: Decimal = Field(default=Decimal("0"), ge=0)
    active: bool = True
    cities: list[SurchargeConfigCityIn] = Field(default_factory=list)

    @field_validator("province_code", "province_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        return _trim_or_none(v)

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.province_mode not in _ALLOWED_PROVINCE_MODE:
            raise ValueError("province_mode must be one of: province / cities")

        if not self.province_code:
            raise ValueError("province_code is required")

        if self.province_mode == "province":
            if self.cities:
                raise ValueError("cities must be empty when province_mode=province")
            return self

        if self.province_mode == "cities":
            if self.fixed_amount != Decimal("0"):
                raise ValueError("fixed_amount must be 0 when province_mode=cities")
            return self

        return self


class SurchargeConfigUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    province_code: Optional[str] = Field(None, min_length=1, max_length=32)
    province_name: Optional[str] = Field(None, max_length=64)

    province_mode: Optional[Literal["province", "cities"]] = None

    fixed_amount: Optional[Decimal] = Field(None, ge=0)
    active: Optional[bool] = None
    cities: Optional[list[SurchargeConfigCityIn]] = None

    @field_validator("province_code", "province_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        return _trim_or_none(v)

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.province_mode is None:
            return self

        if self.province_mode not in _ALLOWED_PROVINCE_MODE:
            raise ValueError("province_mode must be one of: province / cities")

        if self.province_mode == "province":
            if self.cities not in (None, []):
                raise ValueError("cities must be empty when province_mode=province")
            return self

        if self.province_mode == "cities":
            if self.fixed_amount not in (None, Decimal("0")):
                raise ValueError("fixed_amount must be 0 when province_mode=cities")
            return self

        return self


class SurchargeConfigBatchProvinceItemIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    province_code: str = Field(..., min_length=1, max_length=32)
    province_name: Optional[str] = Field(None, max_length=64)
    fixed_amount: Decimal = Field(..., ge=0)
    active: bool = True

    @field_validator("province_code", "province_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        return _trim_or_none(v)

    @model_validator(mode="after")
    def _validate_shape(self):
        if not self.province_code:
            raise ValueError("province_code is required")
        return self


class SurchargeConfigBatchProvinceCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[SurchargeConfigBatchProvinceItemIn] = Field(..., min_length=1)


class SurchargeConfigBatchProvinceSkippedOut(BaseModel):
    province_code: str
    province_name: Optional[str] = None
    reason: Literal["already_exists", "duplicate_in_payload"]


class SurchargeConfigBatchProvinceCreateOut(BaseModel):
    created: list[SurchargeConfigOut] = Field(default_factory=list)
    skipped: list[SurchargeConfigBatchProvinceSkippedOut] = Field(default_factory=list)


class SurchargeCityContainerCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    province_code: str = Field(..., min_length=1, max_length=32)
    province_name: Optional[str] = Field(None, max_length=64)
    active: bool = True

    @field_validator("province_code", "province_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        return _trim_or_none(v)

    @model_validator(mode="after")
    def _validate_shape(self):
        if not self.province_code:
            raise ValueError("province_code is required")
        return self
