from pydantic import BaseModel


class StockAdjIn(BaseModel):
    item_id: int
    delta: int
    reason: str | None = None


class StockAdjOut(BaseModel):
    item_id: int
    qty_available: int
