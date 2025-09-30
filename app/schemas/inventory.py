# app/schemas/inventory.py
from datetime import datetime

from pydantic import BaseModel

from app.models.inventory import MovementType


class InventoryMovementCreate(BaseModel):
    item_sku: str
    from_location_id: str | None = None
    to_location_id: str | None = None
    quantity: float
    movement_type: MovementType


class InventoryMovementOut(InventoryMovementCreate):
    id: str
    timestamp: datetime

    class Config:
        from_attributes = True
