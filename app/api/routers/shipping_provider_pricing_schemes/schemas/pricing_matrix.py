# app/api/routers/shipping_provider_pricing_schemes/schemas/pricing_matrix.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PricingMatrixOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    min_kg: Decimal
    max_kg: Optional[Decimal] = None

    pricing_mode: str  # flat / linear_total / step_over / manual_quote
    flat_amount: Optional[Decimal] = None
    base_amount: Optional[Decimal] = None
    rate_per_kg: Optional[Decimal] = None
    base_kg: Optional[Decimal] = None

    active: bool


class PricingMatrixCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_kg: Decimal = Field(..., ge=0)
    max_kg: Optional[Decimal] = Field(None, ge=0)

    pricing_mode: str = Field(..., min_length=1, max_length=32)
    flat_amount: Optional[Decimal] = Field(None, ge=0)
    base_amount: Optional[Decimal] = Field(None, ge=0)
    rate_per_kg: Optional[Decimal] = Field(None, ge=0)
    base_kg: Optional[Decimal] = Field(None, ge=0)

    active: bool = True

    @model_validator(mode="after")
    def _validate_range(self):
        if self.max_kg is not None:
            if self.max_kg == Decimal("0"):
                raise ValueError("max_kg cannot be 0; use null to represent infinity")
            if self.max_kg <= self.min_kg:
                raise ValueError("max_kg must be > min_kg")
        return self


class PricingMatrixUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_kg: Optional[Decimal] = Field(None, ge=0)
    max_kg: Optional[Decimal] = Field(None, ge=0)

    pricing_mode: Optional[str] = Field(None, min_length=1, max_length=32)
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
        return self
