# app/schemas/items.py

from pydantic import BaseModel


class ItemCreate(BaseModel):
    sku: str
    name: str
    description: str | None = None
    unit_of_measure: str | None = None


class ItemOut(ItemCreate):
    id: str

    class Config:
        from_attributes = True
