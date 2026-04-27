# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/jd/service_order_detail.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from .base_client import BaseJdClient
from .repository import get_credential_by_store_platform, require_enabled_jd_app_config
from .settings import build_jd_jos_config_from_model


JD_PLATFORM = "jd"
JD_ORDER_GET_METHOD = "jingdong.pop.order.get"


class JdOrderDetailServiceError(Exception):
    """OMS 京东订单详情服务异常。"""


@dataclass(frozen=True)
class JdOrderDetailItem:
    sku_id: str | None = None
    outer_sku_id: str | None = None
    ware_id: str | None = None
    item_name: str | None = None
    item_total: int = 0
    item_price: str | None = None
    sku_name: str | None = None
    gift_point: int | None = None
    raw_item: dict[str, Any] | None = None


@dataclass(frozen=True)
class JdOrderDetail:
    order_id: str
    vender_id: str | None = None
    order_type: str | None = None
    order_state: str | None = None
    buyer_pin: str | None = None
    consignee_name: str | None = None
    consignee_mobile: str | None = None
    consignee_phone: str | None = None
    consignee_province: str | None = None
    consignee_city: str | None = None
    consignee_county: str | None = None
    consignee_town: str | None = None
    consignee_address: str | None = None
    order_remark: str | None = None
    seller_remark: str | None = None
    order_total_price: str | None = None
    order_seller_price: str | None = None
    freight_price: str | None = None
    payment_confirm: str | None = None
    order_start_time: str | None = None
    order_end_time: str | None = None
    modified: str | None = None
    items: list[JdOrderDetailItem] | None = None
    raw_payload: dict[str, Any] | None = None


class JdOrderDetailService:
    """
    JD 订单详情补全第一版。

    当前阶段职责：
    - 使用 order_id 调用 jingdong.pop.order.get
    - 提取收件信息、备注、金额、商品明细
    - 不做 OMS ingest
    - 不做事实表入库
    """

    async def fetch_order_detail(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        order_id: str,
    ) -> JdOrderDetail:
        store_id_int = int(store_id)
        order_id_text = str(order_id or "").strip()

        if store_id_int <= 0:
            raise JdOrderDetailServiceError("store_id must be positive")
        if not order_id_text:
            raise JdOrderDetailServiceError("order_id is required")

        app_config = await require_enabled_jd_app_config(session)
        config = build_jd_jos_config_from_model(app_config)

        credential = await get_credential_by_store_platform(
            session,
            store_id=store_id_int,
            platform=JD_PLATFORM,
        )
        if credential is None:
            raise JdOrderDetailServiceError("jd credential not found")

        client = BaseJdClient(config=config)
        payload = await client.call(
            method=JD_ORDER_GET_METHOD,
            access_token=credential.access_token,
            biz_params={"order_id": order_id_text},
        )

        order_info = self._parse_order_info(payload)
        return self._parse_detail(order_info)

    def _parse_order_info(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        response_obj = self._pick_first_mapping(
            payload,
            "jingdong_pop_order_get_responce",
            "jingdong_pop_order_get_response",
            "order_get_response",
        )
        data_obj = self._pick_first_mapping(
            response_obj,
            "orderDetailInfo",
            "order_detail_info",
            "orderInfo",
            "order_info",
            "result",
        )

        order_info = self._pick_first_mapping(
            data_obj,
            "orderInfo",
            "order_info",
        )
        if not isinstance(order_info, Mapping):
            order_info = data_obj

        order_id = self._first_non_empty_str(
            order_info,
            "order_id",
            "jd_order_id",
            "orderId",
        )
        if not order_id:
            raise JdOrderDetailServiceError(f"jd order detail missing order_id: {payload}")

        return order_info

    def _parse_detail(self, order_info: Mapping[str, Any]) -> JdOrderDetail:
        items: list[JdOrderDetailItem] = []
        items_raw = self._extract_items_list(order_info)
        for item in items_raw:
            gift_point: int | None = None
            raw_gift_point = item.get("gift_point") or item.get("giftPoint")
            if raw_gift_point is not None:
                try:
                    gift_point = int(raw_gift_point)
                except (TypeError, ValueError):
                    gift_point = None

            item_total = 0
            raw_item_total = item.get("item_total") or item.get("itemTotal") or item.get("num")
            if raw_item_total is not None:
                try:
                    item_total = int(raw_item_total)
                except (TypeError, ValueError):
                    item_total = 0

            items.append(
                JdOrderDetailItem(
                    sku_id=self._first_non_empty_str(item, "sku_id", "skuId"),
                    outer_sku_id=self._first_non_empty_str(item, "outer_sku_id", "outerSkuId"),
                    ware_id=self._first_non_empty_str(item, "ware_id", "wareId"),
                    item_name=self._first_non_empty_str(item, "item_name", "skuName", "name"),
                    item_total=item_total,
                    item_price=self._normalize_decimal_text(
                        item.get("item_price") or item.get("jd_price") or item.get("price")
                    ),
                    sku_name=self._first_non_empty_str(item, "sku_name", "saleInfo"),
                    gift_point=gift_point,
                    raw_item=dict(item),
                )
            )

        return JdOrderDetail(
            order_id=self._first_non_empty_str(order_info, "order_id", "jd_order_id", "orderId") or "",
            vender_id=self._first_non_empty_str(order_info, "vender_id", "venderId"),
            order_type=self._first_non_empty_str(order_info, "order_type", "orderType"),
            order_state=self._first_non_empty_str(order_info, "order_state", "orderState"),
            buyer_pin=self._first_non_empty_str(order_info, "buyer_pin", "buyerPin"),
            consignee_name=self._first_non_empty_str(
                order_info,
                "consignee_name",
                "consignee",
                "fullname",
            ),
            consignee_mobile=self._first_non_empty_str(
                order_info,
                "consignee_mobile",
                "mobile",
            ),
            consignee_phone=self._first_non_empty_str(
                order_info,
                "consignee_phone",
                "telephone",
                "phone",
            ),
            consignee_province=self._first_non_empty_str(
                order_info,
                "consignee_province",
                "province",
            ),
            consignee_city=self._first_non_empty_str(
                order_info,
                "consignee_city",
                "city",
            ),
            consignee_county=self._first_non_empty_str(
                order_info,
                "consignee_county",
                "county",
                "district",
            ),
            consignee_town=self._first_non_empty_str(
                order_info,
                "consignee_town",
                "town",
            ),
            consignee_address=self._first_non_empty_str(
                order_info,
                "consignee_address",
                "address",
                "full_address",
            ),
            order_remark=self._first_non_empty_str(order_info, "order_remark", "remark"),
            seller_remark=self._first_non_empty_str(order_info, "seller_remark", "venderRemark"),
            order_total_price=self._normalize_decimal_text(
                order_info.get("order_total_price") or order_info.get("orderTotalPrice")
            ),
            order_seller_price=self._normalize_decimal_text(
                order_info.get("order_seller_price") or order_info.get("orderSellerPrice")
            ),
            freight_price=self._normalize_decimal_text(
                order_info.get("freight_price") or order_info.get("freightPrice")
            ),
            payment_confirm=self._first_non_empty_str(
                order_info,
                "payment_confirm",
                "paymentConfirm",
            ),
            order_start_time=self._first_non_empty_str(
                order_info,
                "order_start_time",
                "orderStartTime",
            ),
            order_end_time=self._first_non_empty_str(
                order_info,
                "order_end_time",
                "orderEndTime",
            ),
            modified=self._first_non_empty_str(
                order_info,
                "modified",
                "modified_time",
                "modifiedTime",
            ),
            items=items,
            raw_payload=dict(order_info),
        )

    def _extract_items_list(self, order_info: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        candidates: list[Any] = [
            order_info.get("itemInfoList"),
            order_info.get("item_info_list"),
            order_info.get("sku_list"),
            order_info.get("items"),
        ]
        for item in candidates:
            if isinstance(item, list):
                return [x for x in item if isinstance(x, Mapping)]
            if isinstance(item, Mapping):
                for key in ("itemInfoList", "item_info_list", "sku_list", "items"):
                    nested = item.get(key)
                    if isinstance(nested, list):
                        return [x for x in nested if isinstance(x, Mapping)]
        return []

    def _pick_first_mapping(self, data: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, Mapping):
                return value
        return data

    def _first_non_empty_str(self, data: Mapping[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = str(data.get(key) or "").strip()
            if value:
                return value
        return None

    def _normalize_decimal_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return str(Decimal(text))
        except (InvalidOperation, ValueError):
            return text
