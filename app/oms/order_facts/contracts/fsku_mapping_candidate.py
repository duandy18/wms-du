from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


MappingStatus = Literal["bound", "unbound", "missing_merchant_code"]


class FskuMappingCandidateOut(BaseModel):
    platform: str

    mirror_id: int
    line_id: int
    collector_order_id: int
    collector_line_id: int

    store_code: str
    collector_store_id: int
    collector_store_name: str

    platform_order_no: str
    merchant_code: Optional[str] = None
    platform_item_id: Optional[str] = None
    platform_sku_id: Optional[str] = None
    title: Optional[str] = None
    quantity: str
    line_amount: Optional[str] = None

    is_bound: bool
    mapping_status: MappingStatus

    binding_id: Optional[int] = None
    fsku_id: Optional[int] = None
    fsku_code: Optional[str] = None
    fsku_name: Optional[str] = None
    fsku_status: Optional[str] = None
    binding_reason: Optional[str] = None
    binding_updated_at: Optional[str] = None


class FskuMappingCandidateListDataOut(BaseModel):
    items: list[FskuMappingCandidateOut] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class FskuMappingCandidateListOut(BaseModel):
    ok: bool = True
    data: FskuMappingCandidateListDataOut
