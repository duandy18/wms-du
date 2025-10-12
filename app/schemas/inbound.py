from datetime import date
from pydantic import BaseModel, Field, field_validator
from typing import Optional

class BarcodeScanIn(BaseModel):
    barcode: str = Field(min_length=4, max_length=128)
    # 可选：客户端直接传数量（若扫码枪有称重/计数功能）
    qty: Optional[int] = Field(default=None, ge=1)

class InboundReceiveIn(BaseModel):
    sku: str = Field(min_length=1)
    qty: int = Field(ge=1)
    batch_code: str = Field(min_length=1, max_length=64)
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None
    ref: str = Field(min_length=1, max_length=64)
    ref_line: str = Field(min_length=1, max_length=64)

    @field_validator("expiry_date")
    @classmethod
    def _check_expiry(cls, v, values):
        pd = values.get("production_date")
        if v and pd and v < pd:
            raise ValueError("Expiry earlier than production")
        return v

class PutawayIn(BaseModel):
    sku: str
    batch_code: str
    qty: int = Field(ge=1)
    to_location_id: int
    ref: str
    ref_line: str

class InboundOut(BaseModel):
    item_id: int
    batch_id: int
    accepted_qty: int

class PutawayOut(BaseModel):
    item_id: int
    batch_id: int
    to_location_id: int
    moved_qty: int
