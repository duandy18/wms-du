# app/api/routers/shipping_provider_pricing_schemes/schemas/scheme.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import WeightSegmentIn
from .destination_group import DestinationGroupOut
from .surcharge import SurchargeOut


class SchemeSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    ord: int
    min_kg: Any
    max_kg: Any = None
    active: bool = True


class SchemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
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

    segments_json: Optional[List[WeightSegmentIn]] = None
    segments_updated_at: Optional[datetime] = None

    segments: List[SchemeSegmentOut] = Field(default_factory=list)

    destination_groups: List[DestinationGroupOut] = Field(default_factory=list)
    surcharges: List[SurchargeOut] = Field(default_factory=list)


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
    active: bool = True
    currency: str = Field(default="CNY", min_length=1, max_length=8)

    default_pricing_mode: str = Field(default="linear_total", min_length=1, max_length=32)

    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    billable_weight_rule: Optional[Dict[str, Any]] = None

    segments_json: Optional[List[WeightSegmentIn]] = None


class SchemeUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    active: Optional[bool] = None

    archived_at: Optional[datetime] = None

    currency: Optional[str] = Field(None, min_length=1, max_length=8)

    default_pricing_mode: Optional[str] = Field(None, min_length=1, max_length=32)

    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    billable_weight_rule: Optional[Dict[str, Any]] = None

    segments_json: Optional[List[WeightSegmentIn]] = None
