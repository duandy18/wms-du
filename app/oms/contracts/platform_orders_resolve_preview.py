# app/oms/contracts/platform_orders_resolve_preview.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PlatformOrderResolvePreviewIn(BaseModel):
    platform: str = Field(..., min_length=1, max_length=50)
    store_id: int = Field(..., ge=1)
    ext_order_no: str = Field(..., min_length=1, max_length=128)


class PlatformOrderResolvePreviewFactLineOut(BaseModel):
    line_no: int
    line_key: str
    locator_kind: Optional[str] = None
    locator_value: Optional[str] = None
    filled_code: Optional[str] = None
    qty: int
    title: Optional[str] = None
    spec: Optional[str] = None
    extras: Optional[Dict[str, Any]] = None


class PlatformOrderResolvePreviewResolvedLineOut(BaseModel):
    filled_code: str
    qty: int
    fsku_id: int
    expanded_items: List[Dict[str, Any]]


class PlatformOrderResolvePreviewItemQtyOut(BaseModel):
    item_id: int
    qty: int
    sku: Optional[str] = None
    name: Optional[str] = None


class PlatformOrderResolvePreviewOut(BaseModel):
    status: str
    ref: str
    platform: str
    store_id: int
    ext_order_no: str
    facts_n: int
    fact_lines: List[PlatformOrderResolvePreviewFactLineOut]
    resolved: List[PlatformOrderResolvePreviewResolvedLineOut]
    unresolved: List[Dict[str, Any]]
    item_qty_map: Dict[str, int]
    item_qty_items: List[PlatformOrderResolvePreviewItemQtyOut]
