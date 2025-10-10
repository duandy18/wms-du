# app/schemas/locations.py


from pydantic import BaseModel, ConfigDict


class WarehouseCreate(BaseModel):
    name: str
    address: str | None = None


class WarehouseUpdate(WarehouseCreate):
    name: str | None = None


class WarehouseOut(WarehouseCreate):
    id: str

    model_config = ConfigDict(from_attributes=True)


class LocationCreate(BaseModel):
    name: str
    warehouse_id: str


class LocationUpdate(LocationCreate):
    name: str | None = None
    warehouse_id: str | None = None


class LocationOut(LocationCreate):
    id: str

    model_config = ConfigDict(from_attributes=True)
