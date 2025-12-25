# app/api/routers/shipping_provider_pricing_schemes/schemas/surcharge.py
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class SurchargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    name: str
    priority: int
    active: bool
    condition_json: Dict[str, Any]
    amount_json: Dict[str, Any]


class SurchargeCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    priority: int = Field(default=100, ge=0)
    active: bool = True
    condition_json: Dict[str, Any]
    amount_json: Dict[str, Any]


class SurchargeUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    priority: Optional[int] = Field(None, ge=0)
    active: Optional[bool] = None
    condition_json: Optional[Dict[str, Any]] = None
    amount_json: Optional[Dict[str, Any]] = None
