from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BatchBase(BaseModel):
    batch_number: str
    production_date: datetime | None = None
    expiration_date: datetime | None = None


class BatchCreate(BatchBase):
    pass


class BatchUpdate(BatchBase):
    batch_number: str | None = None


class BatchOut(BatchBase):
    id: str

    model_config = ConfigDict(from_attributes=True)
