# app/api/routers/shipping_provider_pricing_schemes/schemas/matrix_view.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .surcharge import SurchargeOut


_ALLOWED_PRICING_MODES = {"flat", "linear_total", "step_over", "manual_quote"}


class MatrixGroupProvinceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    province_code: Optional[str] = None
    province_name: Optional[str] = None


class MatrixGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_key: str
    scheme_id: int
    name: str
    active: bool
    provinces: List[MatrixGroupProvinceOut] = Field(default_factory=list)


class MatrixWeightRangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    range_key: str
    min_kg: Decimal
    max_kg: Optional[Decimal] = None
    sort_order: int
    label: str


class MatrixCellOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cell_key: str
    pricing_matrix_id: Optional[int] = None

    group_id: int
    group_key: str
    range_key: str

    pricing_mode: str
    flat_amount: Optional[Decimal] = None
    base_amount: Optional[Decimal] = None
    rate_per_kg: Optional[Decimal] = None
    base_kg: Optional[Decimal] = None
    active: bool


class MatrixViewSchemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_id: int
    shipping_provider_id: int
    shipping_provider_name: str

    name: str
    active: bool
    archived_at: Optional[datetime] = None

    currency: str
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None

    default_pricing_mode: str
    billable_weight_rule: Optional[Dict[str, Any]] = None


class MatrixViewDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheme: MatrixViewSchemeOut
    groups: List[MatrixGroupOut] = Field(default_factory=list)
    weight_ranges: List[MatrixWeightRangeOut] = Field(default_factory=list)
    cells: List[MatrixCellOut] = Field(default_factory=list)
    surcharges: List[SurchargeOut] = Field(default_factory=list)


class MatrixViewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    data: MatrixViewDataOut


# =========================
# PATCH /matrix input
# =========================


class MatrixGroupProvinceIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    province_code: Optional[str] = Field(None, max_length=32)
    province_name: Optional[str] = Field(None, max_length=64)

    @field_validator("province_code", "province_name")
    @classmethod
    def _trim(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        return t or None

    @model_validator(mode="after")
    def _validate_province(self):
        if not (self.province_name or self.province_code):
            raise ValueError("province_name or province_code is required")
        return self


class MatrixGroupIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_key: str = Field(..., min_length=1, max_length=128)
    active: bool = True
    provinces: List[MatrixGroupProvinceIn] = Field(default_factory=list)

    @field_validator("group_key")
    @classmethod
    def _trim_required(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("must not be empty")
        return t


class MatrixWeightRangeIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    range_key: str = Field(..., min_length=1, max_length=128)
    min_kg: Decimal = Field(..., ge=0)
    max_kg: Optional[Decimal] = Field(None, ge=0)
    sort_order: Optional[int] = Field(None, ge=0)

    @field_validator("range_key")
    @classmethod
    def _trim_range_key(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("range_key is required")
        return t

    @model_validator(mode="after")
    def _validate_range(self):
        if self.max_kg is not None:
            if self.max_kg == Decimal("0"):
                raise ValueError("max_kg cannot be 0; use null to represent infinity")
            if self.max_kg <= self.min_kg:
                raise ValueError("max_kg must be > min_kg")
        return self


class MatrixCellIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_key: str = Field(..., min_length=1, max_length=128)
    range_key: str = Field(..., min_length=1, max_length=128)

    pricing_mode: Literal["flat", "linear_total", "step_over", "manual_quote"]
    flat_amount: Optional[Decimal] = Field(None, ge=0)
    base_amount: Optional[Decimal] = Field(None, ge=0)
    rate_per_kg: Optional[Decimal] = Field(None, ge=0)
    base_kg: Optional[Decimal] = Field(None, ge=0)
    active: bool = True

    @field_validator("group_key", "range_key")
    @classmethod
    def _trim_keys(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("key is required")
        return t

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.pricing_mode not in _ALLOWED_PRICING_MODES:
            raise ValueError("pricing_mode must be one of: flat / linear_total / step_over / manual_quote")

        if self.pricing_mode == "flat":
            if self.flat_amount is None:
                raise ValueError("flat pricing_mode requires flat_amount")
            if self.base_amount is not None or self.rate_per_kg is not None or self.base_kg is not None:
                raise ValueError("flat pricing_mode only allows flat_amount")

        if self.pricing_mode == "linear_total":
            if self.rate_per_kg is None:
                raise ValueError("linear_total pricing_mode requires rate_per_kg")
            if self.flat_amount is not None or self.base_kg is not None:
                raise ValueError("linear_total pricing_mode does not allow flat_amount or base_kg")

        if self.pricing_mode == "step_over":
            if self.base_kg is None:
                raise ValueError("step_over pricing_mode requires base_kg")
            if self.base_amount is None:
                raise ValueError("step_over pricing_mode requires base_amount")
            if self.rate_per_kg is None:
                raise ValueError("step_over pricing_mode requires rate_per_kg")
            if self.flat_amount is not None:
                raise ValueError("step_over pricing_mode does not allow flat_amount")

        if self.pricing_mode == "manual_quote":
            if any(v is not None for v in (self.flat_amount, self.base_amount, self.rate_per_kg, self.base_kg)):
                raise ValueError("manual_quote pricing_mode does not allow pricing fields")

        return self


class PricingMatrixPatchIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    groups: List[MatrixGroupIn] = Field(default_factory=list)
    weight_ranges: List[MatrixWeightRangeIn] = Field(default_factory=list)
    cells: List[MatrixCellIn] = Field(default_factory=list)
