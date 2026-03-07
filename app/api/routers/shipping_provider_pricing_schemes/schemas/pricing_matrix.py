# app/api/routers/shipping_provider_pricing_schemes/schemas/pricing_matrix.py
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


_ALLOWED_PRICING_MODES = {"flat", "linear_total", "step_over", "manual_quote"}


class PricingMatrixOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    min_kg: Decimal
    max_kg: Optional[Decimal] = None

    pricing_mode: str
    flat_amount: Optional[Decimal] = None
    base_amount: Optional[Decimal] = None
    rate_per_kg: Optional[Decimal] = None
    base_kg: Optional[Decimal] = None

    active: bool


class PricingMatrixCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_kg: Decimal = Field(..., ge=0)
    max_kg: Optional[Decimal] = Field(None, ge=0)

    pricing_mode: Literal["flat", "linear_total", "step_over", "manual_quote"]
    flat_amount: Optional[Decimal] = Field(None, ge=0)
    base_amount: Optional[Decimal] = Field(None, ge=0)
    rate_per_kg: Optional[Decimal] = Field(None, ge=0)
    base_kg: Optional[Decimal] = Field(None, ge=0)

    active: bool = True

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.max_kg is not None:
            if self.max_kg == Decimal("0"):
                raise ValueError("max_kg cannot be 0; use null to represent infinity")
            if self.max_kg <= self.min_kg:
                raise ValueError("max_kg must be > min_kg")

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


class PricingMatrixUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_kg: Optional[Decimal] = Field(None, ge=0)
    max_kg: Optional[Decimal] = Field(None, ge=0)

    pricing_mode: Optional[Literal["flat", "linear_total", "step_over", "manual_quote"]] = None
    flat_amount: Optional[Decimal] = Field(None, ge=0)
    base_amount: Optional[Decimal] = Field(None, ge=0)
    rate_per_kg: Optional[Decimal] = Field(None, ge=0)
    base_kg: Optional[Decimal] = Field(None, ge=0)

    active: Optional[bool] = None

    @model_validator(mode="after")
    def _validate_range(self):
        if self.max_kg is not None and self.max_kg == Decimal("0"):
            raise ValueError("max_kg cannot be 0; use null to represent infinity")
        if self.max_kg is not None and self.min_kg is not None:
            if self.max_kg <= self.min_kg:
                raise ValueError("max_kg must be > min_kg")

        if self.pricing_mode is not None and self.pricing_mode not in _ALLOWED_PRICING_MODES:
            raise ValueError("pricing_mode must be one of: flat / linear_total / step_over / manual_quote")

        return self


class PricingMatrixReplaceRowIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_kg: Decimal = Field(..., ge=0)
    max_kg: Optional[Decimal] = Field(None, ge=0)

    pricing_mode: Literal["flat", "linear_total", "step_over", "manual_quote"]
    flat_amount: Optional[Decimal] = Field(None, ge=0)
    base_amount: Optional[Decimal] = Field(None, ge=0)
    rate_per_kg: Optional[Decimal] = Field(None, ge=0)
    base_kg: Optional[Decimal] = Field(None, ge=0)

    active: bool = True

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.max_kg is not None:
            if self.max_kg == Decimal("0"):
                raise ValueError("max_kg cannot be 0; use null to represent infinity")
            if self.max_kg <= self.min_kg:
                raise ValueError("max_kg must be > min_kg")

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


class PricingMatrixReplaceIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rows: list[PricingMatrixReplaceRowIn] = Field(default_factory=list, min_length=1)


class PricingMatrixReplaceOut(BaseModel):
    ok: bool = True
    group_id: int
    replaced_count: int
    rows: list[PricingMatrixOut] = Field(default_factory=list)
