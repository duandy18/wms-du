# app/schemas/locations.py

from pydantic import BaseModel


class WarehouseCreate(BaseModel):
    name: str
    address: str | None = None


class WarehouseOut(WarehouseCreate):
    id: str

    class Config:
        from_attributes = True


class LocationCreate(BaseModel):
    name: str
    warehouse_id: str


class LocationOut(LocationCreate):
    id: str

    class Config:
        from_attributes = True
