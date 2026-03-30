from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class TaobaoOrderLedgerRowOut(BaseModel):
    id: int
    store_id: int
    tid: str
    status: Optional[str] = None
    type: Optional[str] = None
    created: Optional[str] = None
    pay_time: Optional[str] = None
    payment: Optional[str] = None
    total_fee: Optional[str] = None
    pulled_at: Optional[str] = None
    last_synced_at: Optional[str] = None


class TaobaoOrderLedgerListOut(BaseModel):
    ok: bool = True
    data: List[TaobaoOrderLedgerRowOut]


class TaobaoOrderLedgerItemOut(BaseModel):
    id: int
    taobao_order_id: int
    tid: str
    oid: str
    num_iid: Optional[str] = None
    sku_id: Optional[str] = None
    outer_iid: Optional[str] = None
    outer_sku_id: Optional[str] = None
    title: Optional[str] = None
    price: Optional[str] = None
    num: int
    payment: Optional[str] = None
    total_fee: Optional[str] = None
    sku_properties_name: Optional[str] = None
    raw_item_payload: Any = None


class TaobaoOrderLedgerDetailOut(BaseModel):
    id: int
    store_id: int
    tid: str
    status: Optional[str] = None
    type: Optional[str] = None
    buyer_nick: Optional[str] = None
    buyer_open_uid: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_mobile: Optional[str] = None
    receiver_phone: Optional[str] = None
    receiver_state: Optional[str] = None
    receiver_city: Optional[str] = None
    receiver_district: Optional[str] = None
    receiver_town: Optional[str] = None
    receiver_address: Optional[str] = None
    receiver_zip: Optional[str] = None
    buyer_memo: Optional[str] = None
    buyer_message: Optional[str] = None
    seller_memo: Optional[str] = None
    seller_flag: Optional[int] = None
    payment: Optional[str] = None
    total_fee: Optional[str] = None
    post_fee: Optional[str] = None
    coupon_fee: Optional[str] = None
    created: Optional[str] = None
    pay_time: Optional[str] = None
    modified: Optional[str] = None
    raw_summary_payload: Any = None
    raw_detail_payload: Any = None
    pulled_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    items: List[TaobaoOrderLedgerItemOut]


class TaobaoOrderLedgerDetailEnvelopeOut(BaseModel):
    ok: bool = True
    data: TaobaoOrderLedgerDetailOut
