# Module split: Taobao platform order detail service.
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_order_ingestion.taobao.contracts import TaobaoTopRequest
from app.platform_order_ingestion.taobao.errors import TaobaoTopError
from app.platform_order_ingestion.taobao.repository import (
    get_credential_by_store_platform,
    require_enabled_taobao_app_config,
)
from app.platform_order_ingestion.taobao.settings import build_taobao_top_config_from_model
from app.platform_order_ingestion.taobao.top_client import TaobaoTopClient


TAOBAO_PLATFORM = "taobao"
TAOBAO_TRADE_FULLINFO_GET_METHOD = "taobao.trade.fullinfo.get"

TAOBAO_TRADE_DETAIL_FIELDS = ",".join(
    [
        "tid",
        "status",
        "type",
        "buyer_nick",
        "buyer_open_uid",
        "receiver_name",
        "receiver_mobile",
        "receiver_phone",
        "receiver_state",
        "receiver_city",
        "receiver_district",
        "receiver_town",
        "receiver_address",
        "receiver_zip",
        "buyer_memo",
        "buyer_message",
        "seller_memo",
        "seller_flag",
        "payment",
        "total_fee",
        "post_fee",
        "coupon_fee",
        "created",
        "pay_time",
        "modified",
        "orders",
    ]
)


class TaobaoOrderDetailServiceError(Exception):
    """淘宝订单详情服务异常。"""


@dataclass(frozen=True)
class TaobaoOrderDetailItem:
    oid: str
    num_iid: str | None = None
    sku_id: str | None = None
    outer_iid: str | None = None
    outer_sku_id: str | None = None
    title: str | None = None
    price: str | None = None
    num: int = 0
    payment: str | None = None
    total_fee: str | None = None
    sku_properties_name: str | None = None
    raw_item: dict[str, Any] | None = None


@dataclass(frozen=True)
class TaobaoOrderDetail:
    tid: str
    status: str | None = None
    type: str | None = None
    buyer_nick: str | None = None
    buyer_open_uid: str | None = None
    receiver_name: str | None = None
    receiver_mobile: str | None = None
    receiver_phone: str | None = None
    receiver_state: str | None = None
    receiver_city: str | None = None
    receiver_district: str | None = None
    receiver_town: str | None = None
    receiver_address: str | None = None
    receiver_zip: str | None = None
    buyer_memo: str | None = None
    buyer_message: str | None = None
    seller_memo: str | None = None
    seller_flag: int | None = None
    payment: str | None = None
    total_fee: str | None = None
    post_fee: str | None = None
    coupon_fee: str | None = None
    created: str | None = None
    pay_time: str | None = None
    modified: str | None = None
    items: list[TaobaoOrderDetailItem] | None = None
    raw_payload: dict[str, Any] | None = None


class TaobaoOrderDetailService:
    """
    淘宝订单详情补全服务。

    职责：
    - 使用 tid 调用 taobao.trade.fullinfo.get；
    - 提取订单头和子订单原生字段；
    - 不写 taobao_orders / taobao_order_items；
    - 不写 platform_order_lines；
    - 不做 FSKU / SKU 映射。
    """

    async def fetch_order_detail(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        tid: str,
    ) -> TaobaoOrderDetail:
        store_id_int = int(store_id)
        tid_text = str(tid or "").strip()

        if store_id_int <= 0:
            raise TaobaoOrderDetailServiceError("store_id must be positive")
        if not tid_text:
            raise TaobaoOrderDetailServiceError("tid is required")

        app_config = await require_enabled_taobao_app_config(session)
        config = build_taobao_top_config_from_model(app_config)

        credential = await get_credential_by_store_platform(
            session,
            store_id=store_id_int,
            platform=TAOBAO_PLATFORM,
        )
        if credential is None:
            raise TaobaoOrderDetailServiceError("taobao credential not found")

        request = TaobaoTopRequest(
            method=TAOBAO_TRADE_FULLINFO_GET_METHOD,
            session=credential.access_token,
            biz_params={
                "fields": TAOBAO_TRADE_DETAIL_FIELDS,
                "tid": tid_text,
            },
        )

        client = TaobaoTopClient(config=config)
        try:
            response = await client.call(request)
        except TaobaoTopError as exc:
            raise TaobaoOrderDetailServiceError(f"taobao trade detail request failed: {exc}") from exc

        trade = self._parse_trade_info(response.body)
        return self._parse_detail(trade)

    def _parse_trade_info(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        candidates = [
            body.get("trade"),
            body.get("trade_fullinfo_get_response"),
            body,
        ]
        for item in candidates:
            if isinstance(item, Mapping):
                trade = item.get("trade") if "trade" in item else item
                if isinstance(trade, Mapping):
                    tid = self._first_non_empty_str(trade, "tid", "trade_id")
                    if tid:
                        return trade

        raise TaobaoOrderDetailServiceError(f"taobao trade detail missing tid: {body}")

    def _parse_detail(self, trade: Mapping[str, Any]) -> TaobaoOrderDetail:
        tid = self._first_non_empty_str(trade, "tid", "trade_id") or ""
        items = self._parse_items(trade)

        return TaobaoOrderDetail(
            tid=tid,
            status=self._first_non_empty_str(trade, "status", "trade_status"),
            type=self._first_non_empty_str(trade, "type"),
            buyer_nick=self._first_non_empty_str(trade, "buyer_nick"),
            buyer_open_uid=self._first_non_empty_str(trade, "buyer_open_uid"),
            receiver_name=self._first_non_empty_str(trade, "receiver_name"),
            receiver_mobile=self._first_non_empty_str(trade, "receiver_mobile"),
            receiver_phone=self._first_non_empty_str(trade, "receiver_phone"),
            receiver_state=self._first_non_empty_str(trade, "receiver_state"),
            receiver_city=self._first_non_empty_str(trade, "receiver_city"),
            receiver_district=self._first_non_empty_str(trade, "receiver_district"),
            receiver_town=self._first_non_empty_str(trade, "receiver_town"),
            receiver_address=self._first_non_empty_str(trade, "receiver_address"),
            receiver_zip=self._first_non_empty_str(trade, "receiver_zip"),
            buyer_memo=self._first_non_empty_str(trade, "buyer_memo"),
            buyer_message=self._first_non_empty_str(trade, "buyer_message"),
            seller_memo=self._first_non_empty_str(trade, "seller_memo"),
            seller_flag=self._optional_int(trade.get("seller_flag")),
            payment=self._money_text(trade.get("payment")),
            total_fee=self._money_text(trade.get("total_fee")),
            post_fee=self._money_text(trade.get("post_fee")),
            coupon_fee=self._money_text(trade.get("coupon_fee")),
            created=self._first_non_empty_str(trade, "created"),
            pay_time=self._first_non_empty_str(trade, "pay_time"),
            modified=self._first_non_empty_str(trade, "modified"),
            items=items,
            raw_payload=dict(trade),
        )

    def _parse_items(self, trade: Mapping[str, Any]) -> list[TaobaoOrderDetailItem]:
        raw_items = self._extract_orders_list(trade)
        rows: list[TaobaoOrderDetailItem] = []

        for item in raw_items:
            if not isinstance(item, Mapping):
                continue

            oid = self._first_non_empty_str(item, "oid", "order_id")
            if not oid:
                continue

            rows.append(
                TaobaoOrderDetailItem(
                    oid=oid,
                    num_iid=self._first_non_empty_str(item, "num_iid"),
                    sku_id=self._first_non_empty_str(item, "sku_id"),
                    outer_iid=self._first_non_empty_str(item, "outer_iid"),
                    outer_sku_id=self._first_non_empty_str(item, "outer_sku_id"),
                    title=self._first_non_empty_str(item, "title"),
                    price=self._money_text(item.get("price")),
                    num=int(self._optional_int(item.get("num")) or 0),
                    payment=self._money_text(item.get("payment")),
                    total_fee=self._money_text(item.get("total_fee")),
                    sku_properties_name=self._first_non_empty_str(item, "sku_properties_name"),
                    raw_item=dict(item),
                )
            )

        return rows

    def _extract_orders_list(self, trade: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        orders = trade.get("orders")
        if isinstance(orders, list):
            return [x for x in orders if isinstance(x, Mapping)]
        if isinstance(orders, Mapping):
            nested = orders.get("order")
            if isinstance(nested, list):
                return [x for x in nested if isinstance(x, Mapping)]
            if isinstance(nested, Mapping):
                return [nested]
        return []

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _money_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return str(Decimal(text).quantize(Decimal("0.01")))
        except (InvalidOperation, ValueError):
            return text

    def _first_non_empty_str(self, data: Mapping[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None
