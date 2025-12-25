# app/api/routers/shipping_provider_pricing_schemes/schemas/bracket.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ZoneBracketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    zone_id: int
    min_kg: Decimal
    max_kg: Optional[Decimal] = None

    pricing_mode: str  # flat / linear_total / step_over / manual_quote
    flat_amount: Optional[Decimal] = None
    base_amount: Optional[Decimal] = None
    rate_per_kg: Optional[Decimal] = None

    # step_over: 首重（kg）
    base_kg: Optional[Decimal] = None

    # Mirror field (DB enforced): always present for UI/diagnostics
    price_json: Dict[str, Any] = Field(default_factory=dict)

    active: bool


class ZoneBracketCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_kg: Decimal = Field(..., ge=0)
    max_kg: Optional[Decimal] = Field(None, ge=0)

    pricing_mode: str = Field(
        ..., min_length=1, max_length=32
    )  # flat / linear_total / step_over / manual_quote
    flat_amount: Optional[Decimal] = Field(None, ge=0)
    base_amount: Optional[Decimal] = Field(None, ge=0)
    rate_per_kg: Optional[Decimal] = Field(None, ge=0)

    # step_over
    base_kg: Optional[Decimal] = Field(None, ge=0)

    active: bool = True

    @model_validator(mode="after")
    def _validate_range(self):
        # ✅ 语义铁律：∞=NULL；max_kg=0 禁止；max>min
        if self.max_kg is not None:
            if self.max_kg == Decimal("0"):
                raise ValueError("max_kg cannot be 0; use null to represent infinity")
            if self.max_kg <= self.min_kg:
                raise ValueError("max_kg must be > min_kg")
        return self


class ZoneBracketUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_kg: Optional[Decimal] = Field(None, ge=0)
    max_kg: Optional[Decimal] = Field(None, ge=0)

    pricing_mode: Optional[str] = Field(
        None, min_length=1, max_length=32
    )  # flat / linear_total / step_over / manual_quote
    flat_amount: Optional[Decimal] = Field(None, ge=0)
    base_amount: Optional[Decimal] = Field(None, ge=0)
    rate_per_kg: Optional[Decimal] = Field(None, ge=0)

    # step_over
    base_kg: Optional[Decimal] = Field(None, ge=0)

    active: Optional[bool] = None

    @model_validator(mode="after")
    def _validate_range(self):
        # Update 场景下，如果只更新 max_kg（min_kg 不在 payload），routes 会用 DB 现值补齐后再做严格校验。
        # 这里先做最基本的：禁止 max_kg=0。
        if self.max_kg is not None and self.max_kg == Decimal("0"):
            raise ValueError("max_kg cannot be 0; use null to represent infinity")
        # 如果同时传了 min/max，则也可在 schema 先拦一层
        if self.max_kg is not None and self.min_kg is not None:
            if self.max_kg <= self.min_kg:
                raise ValueError("max_kg must be > min_kg")
        return self
