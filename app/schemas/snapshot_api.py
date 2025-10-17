from __future__ import annotations

from pydantic import BaseModel, Field


class TopLocation(BaseModel):
    location_id: int
    qty: int


class InventoryItem(BaseModel):
    item_id: int
    name: str
    spec: str | None = None
    total_qty: int = Field(ge=0)
    top2_locations: list[TopLocation]
    earliest_expiry: str | None = None  # ISO date (YYYY-MM-DD) 或 None
    near_expiry: bool


class InventorySnapshotResponse(BaseModel):
    items: list[InventoryItem]
