# app/api/routers/shipping_provider_pricing_schemes/schemas/scheme.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .destination_group import DestinationGroupOut
from .surcharge import SurchargeConfigOut

_ALLOWED_SCHEME_STATUS = {"draft", "active", "archived"}
_ALLOWED_BILLABLE_STRATEGY = {"actual_only", "max_actual_volume"}
_ALLOWED_ROUNDING_MODE = {"none", "ceil"}
_ALLOWED_DEFAULT_PRICING_MODE = {"flat", "linear_total", "step_over"}


class SchemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipping_provider_id: int
    shipping_provider_name: str

    name: str
    status: str
    archived_at: Optional[datetime] = None

    currency: str
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None

    default_pricing_mode: str

    billable_weight_strategy: str
    volume_divisor: Optional[int] = None
    rounding_mode: str
    rounding_step_kg: Optional[float] = None
    min_billable_weight_kg: Optional[float] = None

    destination_groups: List[DestinationGroupOut] = Field(default_factory=list)
    surcharge_configs: List[SurchargeConfigOut] = Field(default_factory=list)


class SchemeListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    data: List[SchemeOut]


class SchemeDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool = True
    data: SchemeOut


class SchemeCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    warehouse_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=128)
    currency: str = Field(default="CNY", min_length=1, max_length=8)

    default_pricing_mode: str = Field(default="linear_total", min_length=1, max_length=32)

    billable_weight_strategy: str = Field(default="actual_only", min_length=1, max_length=32)
    volume_divisor: Optional[int] = Field(default=None, ge=1)
    rounding_mode: str = Field(default="none", min_length=1, max_length=16)
    rounding_step_kg: Optional[float] = Field(default=None, gt=0)
    min_billable_weight_kg: Optional[float] = Field(default=None, gt=0)

    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.default_pricing_mode not in _ALLOWED_DEFAULT_PRICING_MODE:
            raise ValueError("default_pricing_mode must be one of: flat / linear_total / step_over")

        if self.billable_weight_strategy not in _ALLOWED_BILLABLE_STRATEGY:
            raise ValueError("billable_weight_strategy must be one of: actual_only / max_actual_volume")

        if self.rounding_mode not in _ALLOWED_ROUNDING_MODE:
            raise ValueError("rounding_mode must be one of: none / ceil")

        if self.billable_weight_strategy == "actual_only":
            if self.volume_divisor is not None:
                raise ValueError("volume_divisor must be empty when billable_weight_strategy=actual_only")

        if self.billable_weight_strategy == "max_actual_volume":
            if self.volume_divisor is None:
                raise ValueError("volume_divisor is required when billable_weight_strategy=max_actual_volume")

        if self.rounding_mode == "none":
            if self.rounding_step_kg is not None:
                raise ValueError("rounding_step_kg must be empty when rounding_mode=none")

        if self.rounding_mode == "ceil":
            if self.rounding_step_kg is None:
                raise ValueError("rounding_step_kg is required when rounding_mode=ceil")

        return self


class SchemeUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    status: Optional[str] = Field(None, min_length=1, max_length=16)

    currency: Optional[str] = Field(None, min_length=1, max_length=8)
    default_pricing_mode: Optional[str] = Field(None, min_length=1, max_length=32)

    billable_weight_strategy: Optional[str] = Field(None, min_length=1, max_length=32)
    volume_divisor: Optional[int] = Field(default=None, ge=1)
    rounding_mode: Optional[str] = Field(None, min_length=1, max_length=16)
    rounding_step_kg: Optional[float] = Field(default=None, gt=0)
    min_billable_weight_kg: Optional[float] = Field(default=None, gt=0)

    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None

    @model_validator(mode="after")
    def _validate_shape(self):
        if self.status is not None and self.status not in _ALLOWED_SCHEME_STATUS:
            raise ValueError("status must be one of: draft / active / archived")

        if self.default_pricing_mode is not None and self.default_pricing_mode not in _ALLOWED_DEFAULT_PRICING_MODE:
            raise ValueError("default_pricing_mode must be one of: flat / linear_total / step_over")

        if self.billable_weight_strategy is not None and self.billable_weight_strategy not in _ALLOWED_BILLABLE_STRATEGY:
            raise ValueError("billable_weight_strategy must be one of: actual_only / max_actual_volume")

        if self.rounding_mode is not None and self.rounding_mode not in _ALLOWED_ROUNDING_MODE:
            raise ValueError("rounding_mode must be one of: none / ceil")

        # 局部更新场景下，只做字段级合法性；跨字段完整性由 service 再合并当前值后校验
        return self
