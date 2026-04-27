# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/pdd/contracts.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PddOrderListRequest:
    """
    pdd.order.list.get 最小请求参数。
    """

    start_confirm_at: str
    end_confirm_at: str
    order_status: int = 1
    page: int = 1
    page_size: int = 50

    def to_business_params(self) -> Dict[str, Any]:
        return {
            "start_confirm_at": self.start_confirm_at,
            "end_confirm_at": self.end_confirm_at,
            "order_status": self.order_status,
            "page": self.page,
            "page_size": self.page_size,
        }


@dataclass(frozen=True)
class PddOrderSummary:
    """
    PDD 订单最小摘要。
    """

    platform_order_id: str
    order_status: Optional[int]
    confirm_at: Optional[str]
    receiver_name_masked: Optional[str]
    receiver_phone_masked: Optional[str]
    receiver_address_summary_masked: Optional[str]
    buyer_memo: Optional[str]
    items_count: int
    raw_order: Dict[str, Any]


@dataclass(frozen=True)
class PddOrderPageResult:
    """
    PDD 订单列表单页结果。
    """

    page: int
    page_size: int
    orders_count: int
    has_more: bool
    orders: List[PddOrderSummary]
    raw_payload: Dict[str, Any]
    start_confirm_at: str
    end_confirm_at: str


@dataclass(frozen=True)
class PddOrderDetailItem:
    goods_id: Optional[str]
    goods_name: Optional[str]
    sku_id: Optional[str]
    outer_id: Optional[str]
    goods_count: int
    goods_price: Optional[int]
    raw_item: Dict[str, Any]


@dataclass(frozen=True)
class PddOrderDetail:
    order_sn: str
    province: Optional[str]
    city: Optional[str]
    town: Optional[str]
    receiver_name_masked: Optional[str]
    receiver_phone_masked: Optional[str]
    receiver_address_masked: Optional[str]
    buyer_memo: Optional[str]
    remark: Optional[str]
    items: List[PddOrderDetailItem]
    raw_payload: Dict[str, Any]
