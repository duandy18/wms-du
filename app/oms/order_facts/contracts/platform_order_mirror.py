from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


OmsMirrorPlatform = Literal["pdd", "taobao", "jd"]


class PlatformOrderMirrorLineImportIn(BaseModel):
    collector_line_id: int = Field(..., ge=1)
    collector_order_id: int = Field(..., ge=1)
    platform_order_no: str = Field(..., min_length=1, max_length=128)

    merchant_sku: Optional[str] = Field(None, max_length=128)
    platform_item_id: Optional[str] = Field(None, max_length=128)
    platform_sku_id: Optional[str] = Field(None, max_length=128)
    title: Optional[str] = Field(None, max_length=255)

    quantity: Decimal = Decimal("0")
    unit_price: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None

    platform_fields: dict[str, Any] = Field(default_factory=dict)
    raw_item_payload: Any = None


class PlatformOrderMirrorImportIn(BaseModel):
    collector_order_id: int = Field(..., ge=1)
    collector_store_id: int = Field(..., ge=1)
    collector_store_code: str = Field(..., min_length=1, max_length=128)
    collector_store_name: str = Field(..., min_length=1, max_length=255)

    platform: OmsMirrorPlatform
    platform_order_no: str = Field(..., min_length=1, max_length=128)
    platform_status: Optional[str] = Field(None, max_length=64)

    source_updated_at: Optional[str] = None
    pulled_at: Optional[str] = None
    last_synced_at: Optional[str] = None

    receiver: dict[str, Any] = Field(default_factory=dict)
    amounts: dict[str, Any] = Field(default_factory=dict)
    platform_fields: dict[str, Any] = Field(default_factory=dict)
    raw_refs: dict[str, Any] = Field(default_factory=dict)

    lines: list[PlatformOrderMirrorLineImportIn] = Field(default_factory=list)


class PlatformOrderMirrorLineOut(BaseModel):
    id: int
    collector_line_id: int
    collector_order_id: int
    platform_order_no: str

    merchant_sku: Optional[str] = None
    platform_item_id: Optional[str] = None
    platform_sku_id: Optional[str] = None
    title: Optional[str] = None

    quantity: str
    unit_price: Optional[str] = None
    line_amount: Optional[str] = None

    platform_fields: dict[str, Any] = Field(default_factory=dict)
    raw_item_payload: Any = None


class PlatformOrderMirrorOut(BaseModel):
    id: int
    collector_order_id: int
    collector_store_id: int
    collector_store_code: str
    collector_store_name: str

    wms_store_id: Optional[int] = None

    platform: OmsMirrorPlatform
    platform_order_no: str
    platform_status: Optional[str] = None

    import_status: str
    mirror_status: str

    source_updated_at: Optional[str] = None
    pulled_at: Optional[str] = None
    collector_last_synced_at: Optional[str] = None
    imported_at: Optional[str] = None
    last_synced_at: Optional[str] = None

    receiver: dict[str, Any] = Field(default_factory=dict)
    amounts: dict[str, Any] = Field(default_factory=dict)
    platform_fields: dict[str, Any] = Field(default_factory=dict)
    raw_refs: dict[str, Any] = Field(default_factory=dict)

    lines: list[PlatformOrderMirrorLineOut] = Field(default_factory=list)


class PlatformOrderMirrorListOut(BaseModel):
    ok: bool = True
    data: list[PlatformOrderMirrorOut]


class PlatformOrderMirrorEnvelopeOut(BaseModel):
    ok: bool = True
    data: PlatformOrderMirrorOut
