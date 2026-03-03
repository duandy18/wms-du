from pydantic import BaseModel, Field
from typing import Optional


class ItemUomCreate(BaseModel):
    item_id: int
    uom: str = Field(..., min_length=1, max_length=16)
    ratio_to_base: int = Field(..., ge=1)
    display_name: Optional[str] = Field(None, max_length=32)
    is_base: bool = False
    is_purchase_default: bool = False
    is_inbound_default: bool = False
    is_outbound_default: bool = False


class ItemUomUpdate(BaseModel):
    uom: Optional[str] = Field(None, min_length=1, max_length=16)
    ratio_to_base: Optional[int] = Field(None, ge=1)
    display_name: Optional[str] = Field(None, max_length=32)
    is_base: Optional[bool] = None
    is_purchase_default: Optional[bool] = None
    is_inbound_default: Optional[bool] = None
    is_outbound_default: Optional[bool] = None


class ItemUomOut(BaseModel):
    id: int
    item_id: int
    uom: str
    ratio_to_base: int
    display_name: Optional[str]
    is_base: bool
    is_purchase_default: bool
    is_inbound_default: bool
    is_outbound_default: bool

    class Config:
        from_attributes = True
