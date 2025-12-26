# app/api/routers/shipping_provider_pricing_schemes/schemas/segment_template.py
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SegmentTemplateItemIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ord: int = Field(..., ge=0)
    min_kg: Any
    max_kg: Any = None  # null = ∞
    active: bool = True


class SegmentTemplateItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    ord: int
    min_kg: Any
    max_kg: Any = None
    active: bool = True


class SegmentTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    name: str
    status: str
    is_active: bool
    effective_from: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    items: List[SegmentTemplateItemOut] = Field(default_factory=list)


class SegmentTemplateListOut(BaseModel):
    ok: bool = True
    data: List[SegmentTemplateOut]


class SegmentTemplateDetailOut(BaseModel):
    ok: bool = True
    data: SegmentTemplateOut


class SegmentTemplateCreateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    effective_from: Optional[datetime] = None


class SegmentTemplateItemsPutIn(BaseModel):
    items: List[SegmentTemplateItemIn]


class SegmentTemplateItemActivePatchIn(BaseModel):
    active: bool
