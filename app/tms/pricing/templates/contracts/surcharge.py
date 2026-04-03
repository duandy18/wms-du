from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class SurchargeConfigCityIn(BaseModel):
    city_code: str = Field(..., min_length=1, max_length=32)
    city_name: Optional[str] = Field(default=None, max_length=64)
    fixed_amount: Decimal = Field(default=Decimal("0"))
    active: bool = True


class SurchargeConfigCityOut(BaseModel):
    id: int
    config_id: int
    city_code: str
    city_name: Optional[str] = None
    fixed_amount: Decimal
    active: bool


class SurchargeConfigOut(BaseModel):
    id: int
    template_id: int
    province_code: str
    province_name: Optional[str] = None
    province_mode: str
    fixed_amount: Decimal
    active: bool
    cities: list[SurchargeConfigCityOut] = Field(default_factory=list)


class SurchargeConfigCreateIn(BaseModel):
    province_code: str = Field(..., min_length=1, max_length=32)
    province_name: Optional[str] = Field(default=None, max_length=64)
    province_mode: str = Field(default="province", min_length=1, max_length=16)
    fixed_amount: Decimal = Field(default=Decimal("0"))
    active: bool = True
    cities: list[SurchargeConfigCityIn] = Field(default_factory=list)


class SurchargeConfigUpdateIn(BaseModel):
    province_code: Optional[str] = Field(default=None, max_length=32)
    province_name: Optional[str] = Field(default=None, max_length=64)
    province_mode: Optional[str] = Field(default=None, max_length=16)
    fixed_amount: Optional[Decimal] = None
    active: Optional[bool] = None
    cities: Optional[list[SurchargeConfigCityIn]] = None


class SurchargeConfigBatchProvinceItemIn(BaseModel):
    province_code: str = Field(..., min_length=1, max_length=32)
    province_name: Optional[str] = Field(default=None, max_length=64)
    fixed_amount: Decimal = Field(default=Decimal("0"))
    active: bool = True


class SurchargeConfigBatchProvinceCreateIn(BaseModel):
    items: list[SurchargeConfigBatchProvinceItemIn] = Field(default_factory=list)


class SurchargeConfigBatchProvinceCreateOut(BaseModel):
    created: list[SurchargeConfigOut] = Field(default_factory=list)
    skipped: list[dict[str, str | None]] = Field(default_factory=list)


class SurchargeCityContainerCreateIn(BaseModel):
    province_code: str = Field(..., min_length=1, max_length=32)
    province_name: Optional[str] = Field(default=None, max_length=64)
    active: bool = True
