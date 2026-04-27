# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/jd/service_real_pull.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .base_client import BaseJdClient
from .repository import get_credential_by_store_platform, require_enabled_jd_app_config
from .settings import build_jd_jos_config_from_model


JD_PLATFORM = "jd"
JD_ORDER_SEARCH_METHOD = "jingdong.pop.order.search"

DEFAULT_JD_PAGE = 1
DEFAULT_JD_PAGE_SIZE = 20
MAX_JD_PAGE_SIZE = 100
DEFAULT_JD_WINDOW_MINUTES = 30
DEFAULT_JD_SAFETY_BUFFER_SECONDS = 60
MAX_JD_WINDOW_DAYS = 30


class JdRealPullServiceError(Exception):
    """OMS 京东真实拉单异常。"""


@dataclass(frozen=True)
class JdOrderSummary:
    platform_order_id: str
    order_state: str | None = None
    order_type: str | None = None
    order_start_time: str | None = None
    modified: str | None = None
    consignee_name_masked: str | None = None
    consignee_mobile_masked: str | None = None
    consignee_address_summary_masked: str | None = None
    order_remark: str | None = None
    order_total_price: str | None = None
    items_count: int = 0
    raw_order: dict[str, Any] | None = None


@dataclass(frozen=True)
class JdOrderPageResult:
    page: int
    page_size: int
    orders_count: int
    has_more: bool
    start_time: str
    end_time: str
    orders: list[JdOrderSummary]
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class JdRealPullParams:
    store_id: int
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    page: int = DEFAULT_JD_PAGE
    page_size: int = DEFAULT_JD_PAGE_SIZE
    order_state: Optional[str] = None


class JdRealPullService:
    """
    JD 真实拉单第一版。

    当前阶段职责：
    - 使用当前店铺 access_token 调用 jingdong.pop.order.search
    - 以时间窗口拉取订单摘要
    - 返回最小订单摘要
    - 不做 OMS ingest
    - 不做事实表入库
    """

    async def fetch_order_page(
        self,
        *,
        session: AsyncSession,
        params: JdRealPullParams,
    ) -> JdOrderPageResult:
        if params.store_id <= 0:
            raise JdRealPullServiceError("store_id must be positive")
        if params.page <= 0:
            raise JdRealPullServiceError("page must be positive")
        if params.page_size <= 0:
            raise JdRealPullServiceError("page_size must be positive")
        if params.page_size > MAX_JD_PAGE_SIZE:
            raise JdRealPullServiceError(f"page_size must be <= {MAX_JD_PAGE_SIZE}")

        start_text, end_text = self._resolve_time_window(
            start_time=params.start_time,
            end_time=params.end_time,
        )

        app_config = await require_enabled_jd_app_config(session)
        config = build_jd_jos_config_from_model(app_config)

        credential = await get_credential_by_store_platform(
            session,
            store_id=params.store_id,
            platform=JD_PLATFORM,
        )
        if credential is None:
            raise JdRealPullServiceError("jd credential not found")
        if credential.expires_at <= datetime.now(timezone.utc):
            raise JdRealPullServiceError("jd credential expired")

        client = BaseJdClient(config=config)
        payload = await client.call(
            method=JD_ORDER_SEARCH_METHOD,
            access_token=credential.access_token,
            biz_params=self._build_search_biz_params(
                start_time=start_text,
                end_time=end_text,
                page=params.page,
                page_size=params.page_size,
                order_state=params.order_state,
            ),
        )

        orders, has_more = self._parse_order_page(payload, page_size=params.page_size)

        return JdOrderPageResult(
            page=params.page,
            page_size=params.page_size,
            orders_count=len(orders),
            has_more=has_more,
            start_time=start_text,
            end_time=end_text,
            orders=orders,
            raw_payload=payload,
        )

    def _build_search_biz_params(
        self,
        *,
        start_time: str,
        end_time: str,
        page: int,
        page_size: int,
        order_state: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "start_date": start_time,
            "end_date": end_time,
            "page": page,
            "page_size": page_size,
        }
        if order_state:
            payload["order_state"] = order_state
        return payload

    def _resolve_time_window(
        self,
        *,
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> tuple[str, str]:
        now = datetime.now(timezone.utc)

        if not start_time and not end_time:
            end_dt = now
            start_dt = end_dt - timedelta(
                minutes=DEFAULT_JD_WINDOW_MINUTES,
                seconds=DEFAULT_JD_SAFETY_BUFFER_SECONDS,
            )
            return self._format_dt(start_dt), self._format_dt(end_dt)

        if not start_time or not end_time:
            raise JdRealPullServiceError("start_time and end_time must be both provided")

        start_dt = self._parse_dt(start_time)
        end_dt = self._parse_dt(end_time)

        if end_dt <= start_dt:
            raise JdRealPullServiceError("end_time must be greater than start_time")
        if (end_dt - start_dt) > timedelta(days=MAX_JD_WINDOW_DAYS):
            raise JdRealPullServiceError("time window must be <= 30 days")

        safe_start_dt = start_dt - timedelta(seconds=DEFAULT_JD_SAFETY_BUFFER_SECONDS)
        return self._format_dt(safe_start_dt), self._format_dt(end_dt)

    def _parse_order_page(
        self,
        payload: Mapping[str, Any],
        *,
        page_size: int,
    ) -> tuple[list[JdOrderSummary], bool]:
        response_obj = self._pick_first_mapping(
            payload,
            "jingdong_pop_order_search_responce",
            "jingdong_pop_order_search_response",
            "order_search_response",
        )
        data_obj = self._pick_first_mapping(
            response_obj,
            "searchorderinfo_result",
            "search_order_info_result",
            "result",
        )

        orders_raw = self._extract_orders_list(response_obj, data_obj)

        summaries: list[JdOrderSummary] = []
        for order in orders_raw:
            if not isinstance(order, Mapping):
                continue

            platform_order_id = self._first_non_empty_str(
                order,
                "order_id",
                "jd_order_id",
                "orderId",
            )
            if not platform_order_id:
                continue

            consignee_name = self._first_non_empty_str(
                order,
                "consignee",
                "fullname",
                "name",
                "receiver_name",
            )
            consignee_mobile = self._first_non_empty_str(
                order,
                "mobile",
                "consignee_mobile",
                "receiver_mobile",
                "telephone",
            )
            address_summary = self._build_address_summary(order)

            summaries.append(
                JdOrderSummary(
                    platform_order_id=platform_order_id,
                    order_state=self._first_non_empty_str(
                        order,
                        "order_state",
                        "orderState",
                    ),
                    order_type=self._first_non_empty_str(
                        order,
                        "order_type",
                        "orderType",
                    ),
                    order_start_time=self._first_non_empty_str(
                        order,
                        "order_start_time",
                        "orderStartTime",
                    ),
                    modified=self._first_non_empty_str(
                        order,
                        "modified",
                        "modified_time",
                        "modifiedTime",
                    ),
                    consignee_name_masked=consignee_name,
                    consignee_mobile_masked=consignee_mobile,
                    consignee_address_summary_masked=address_summary,
                    order_remark=self._first_non_empty_str(
                        order,
                        "order_remark",
                        "remark",
                    ),
                    order_total_price=self._normalize_decimal_text(
                        order.get("order_total_price") or order.get("orderTotalPrice")
                    ),
                    items_count=self._extract_items_count(order),
                    raw_order=dict(order),
                )
            )

        has_more = self._extract_has_more(response_obj, data_obj, len(summaries), page_size)
        return summaries, has_more

    def _extract_orders_list(
        self,
        response_obj: Mapping[str, Any],
        data_obj: Mapping[str, Any],
    ) -> list[Mapping[str, Any]]:
        candidates: list[Any] = [
            data_obj.get("orderInfoList"),
            data_obj.get("order_info_list"),
            data_obj.get("orders"),
            response_obj.get("orderInfoList"),
            response_obj.get("order_info_list"),
            response_obj.get("orders"),
        ]
        for item in candidates:
            if isinstance(item, list):
                return [x for x in item if isinstance(x, Mapping)]
            if isinstance(item, Mapping):
                for key in ("orderInfoList", "order_info_list", "orders"):
                    nested = item.get(key)
                    if isinstance(nested, list):
                        return [x for x in nested if isinstance(x, Mapping)]
        return []

    def _extract_items_count(self, order: Mapping[str, Any]) -> int:
        for key in ("itemInfoList", "item_info_list", "sku_list", "items"):
            raw = order.get(key)
            if isinstance(raw, list):
                return len(raw)
        for key in ("item_total", "itemTotal", "goods_count"):
            raw = order.get(key)
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
        return 0

    def _extract_has_more(
        self,
        response_obj: Mapping[str, Any],
        data_obj: Mapping[str, Any],
        count: int,
        page_size: int,
    ) -> bool:
        for source in (data_obj, response_obj):
            for key in ("hasMore", "has_more", "hasNextPage", "has_next_page"):
                raw = source.get(key)
                if isinstance(raw, bool):
                    return raw
                if isinstance(raw, int):
                    return raw != 0

            total_pages = source.get("pageTotal") or source.get("page_total")
            current_page = source.get("page") or source.get("currentPage") or source.get("current_page")
            try:
                if total_pages is not None and current_page is not None:
                    return int(current_page) < int(total_pages)
            except (TypeError, ValueError):
                pass

        return count >= page_size

    def _build_address_summary(self, order: Mapping[str, Any]) -> str | None:
        parts = [
            self._first_non_empty_str(order, "province", "consignee_province"),
            self._first_non_empty_str(order, "city", "consignee_city"),
            self._first_non_empty_str(order, "county", "district", "consignee_county"),
            self._first_non_empty_str(order, "town", "consignee_town"),
            self._first_non_empty_str(order, "address", "consignee_address", "full_address"),
        ]
        merged = "".join([part for part in parts if part])
        return merged or None

    def _parse_dt(self, value: str) -> datetime:
        text = str(value or "").strip()
        if not text:
            raise JdRealPullServiceError("time value is required")
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise JdRealPullServiceError(
                f"invalid datetime format: {text!r}, expected yyyy-MM-dd HH:mm:ss"
            ) from exc
        return dt.replace(tzinfo=timezone.utc)

    def _format_dt(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

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
