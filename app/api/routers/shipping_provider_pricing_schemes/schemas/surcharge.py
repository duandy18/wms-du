# app/api/routers/shipping_provider_pricing_schemes/schemas/surcharge.py
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SurchargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    name: str
    active: bool
    condition_json: Dict[str, Any]
    amount_json: Dict[str, Any]


class SurchargeCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True
    condition_json: Dict[str, Any]
    amount_json: Dict[str, Any]

    @field_validator("amount_json")
    @classmethod
    def _reject_deprecated_rounding(cls, v: Dict[str, Any]):
        # ✅ amount_json.rounding 已废弃且不再生效
        if isinstance(v, dict) and ("rounding" in v) and (v.get("rounding") is not None):
            raise ValueError("amount_json.rounding is deprecated and ignored; use scheme.billable_weight_rule.rounding")
        return v


class SurchargeUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    active: Optional[bool] = None
    condition_json: Optional[Dict[str, Any]] = None
    amount_json: Optional[Dict[str, Any]] = None

    @field_validator("amount_json")
    @classmethod
    def _reject_deprecated_rounding(cls, v: Optional[Dict[str, Any]]):
        # ✅ amount_json.rounding 已废弃且不再生效
        if v is None:
            return v
        if isinstance(v, dict) and ("rounding" in v) and (v.get("rounding") is not None):
            raise ValueError("amount_json.rounding is deprecated and ignored; use scheme.billable_weight_rule.rounding")
        return v
