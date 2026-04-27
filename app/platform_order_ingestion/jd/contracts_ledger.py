# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class JdOrderLedgerRowOut(BaseModel):
    id: int
    store_id: int
    order_id: str
    order_state: Optional[str] = None
    order_type: Optional[str] = None
    order_start_time: Optional[str] = None
    modified: Optional[str] = None
    order_total_price: Optional[str] = None
    order_seller_price: Optional[str] = None
    pulled_at: Optional[str] = None
    last_synced_at: Optional[str] = None


class JdOrderLedgerListOut(BaseModel):
    ok: bool = True
    data: List[JdOrderLedgerRowOut]


class JdOrderLedgerItemOut(BaseModel):
    id: int
    jd_order_id: int
    order_id: str
    sku_id: Optional[str] = None
    outer_sku_id: Optional[str] = None
    ware_id: Optional[str] = None
    item_name: Optional[str] = None
    item_total: int
    item_price: Optional[str] = None
    sku_name: Optional[str] = None
    gift_point: Optional[int] = None
    raw_item_payload: Any = None


class JdOrderLedgerDetailOut(BaseModel):
    id: int
    store_id: int
    order_id: str
    vender_id: Optional[str] = None
    order_type: Optional[str] = None
    order_state: Optional[str] = None
    buyer_pin: Optional[str] = None
    consignee_name: Optional[str] = None
    consignee_mobile: Optional[str] = None
    consignee_phone: Optional[str] = None
    consignee_province: Optional[str] = None
    consignee_city: Optional[str] = None
    consignee_county: Optional[str] = None
    consignee_town: Optional[str] = None
    consignee_address: Optional[str] = None
    order_remark: Optional[str] = None
    seller_remark: Optional[str] = None
    order_total_price: Optional[str] = None
    order_seller_price: Optional[str] = None
    freight_price: Optional[str] = None
    payment_confirm: Optional[str] = None
    order_start_time: Optional[str] = None
    order_end_time: Optional[str] = None
    modified: Optional[str] = None
    raw_summary_payload: Any = None
    raw_detail_payload: Any = None
    pulled_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    items: List[JdOrderLedgerItemOut]


class JdOrderLedgerDetailEnvelopeOut(BaseModel):
    ok: bool = True
    data: JdOrderLedgerDetailOut
