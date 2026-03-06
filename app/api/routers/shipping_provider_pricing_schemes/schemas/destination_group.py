# app/api/routers/shipping_provider_pricing_schemes/schemas/destination_group.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .pricing_matrix import PricingMatrixOut


class DestinationGroupMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    scope: str
    province_code: Optional[str] = None
    city_code: Optional[str] = None
    province_name: Optional[str] = None
    city_name: Optional[str] = None


class DestinationGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    name: str
    active: bool

    members: List[DestinationGroupMemberOut] = Field(default_factory=list)
    pricing_matrix: List[PricingMatrixOut] = Field(default_factory=list)
