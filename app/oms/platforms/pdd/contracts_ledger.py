from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class PddOrderLedgerRowOut(BaseModel):
    id: int
    store_id: int
    order_sn: str
    order_status: Optional[str] = None
    confirm_at: Optional[str] = None
    goods_amount: Optional[str] = None
    pay_amount: Optional[str] = None
    pulled_at: Optional[str] = None
    last_synced_at: Optional[str] = None


class PddOrderLedgerListOut(BaseModel):
    ok: bool = True
    data: List[PddOrderLedgerRowOut]


class PddOrderLedgerItemOut(BaseModel):
    id: int
    pdd_order_id: int
    order_sn: str
    platform_goods_id: Optional[str] = None
    platform_sku_id: Optional[str] = None
    outer_id: Optional[str] = None
    goods_name: Optional[str] = None
    goods_count: int
    goods_price: Optional[str] = None
    raw_item_payload: Any = None


class PddOrderLedgerDetailOut(BaseModel):
    id: int
    store_id: int
    order_sn: str
    order_status: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    receiver_province: Optional[str] = None
    receiver_city: Optional[str] = None
    receiver_district: Optional[str] = None
    receiver_address: Optional[str] = None
    buyer_memo: Optional[str] = None
    remark: Optional[str] = None
    confirm_at: Optional[str] = None
    goods_amount: Optional[str] = None
    pay_amount: Optional[str] = None
    raw_summary_payload: Any = None
    raw_detail_payload: Any = None
    pulled_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    items: List[PddOrderLedgerItemOut]


class PddOrderLedgerDetailEnvelopeOut(BaseModel):
    ok: bool = True
    data: PddOrderLedgerDetailOut
