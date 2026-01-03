# app/api/routers/shipping_provider_pricing_schemes/schemas/surcharge.py
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class SurchargeUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    active: Optional[bool] = None
    condition_json: Optional[Dict[str, Any]] = None
    amount_json: Optional[Dict[str, Any]] = None
