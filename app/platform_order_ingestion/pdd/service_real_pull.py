# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/pdd/service_real_pull.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .access_repository import get_credential_by_store_platform
from .client import PddOpenClient, PddOpenClientError
from .contracts import (
    PddOrderListRequest,
    PddOrderPageResult,
    PddOrderSummary,
)
from .repository import require_enabled_pdd_app_config
from .settings import build_pdd_open_config_from_model


PDD_PLATFORM = "pdd"
PDD_ORDER_LIST_API_TYPE = "pdd.order.list.get"

DEFAULT_PDD_ORDER_STATUS = 1
DEFAULT_PDD_PAGE = 1
DEFAULT_PDD_PAGE_SIZE = 50
MAX_PDD_PAGE_SIZE = 100
DEFAULT_PDD_WINDOW_MINUTES = 30
DEFAULT_PDD_SAFETY_BUFFER_SECONDS = 60
MAX_PDD_WINDOW_HOURS = 24


class PddRealPullServiceError(Exception):
    """OMS 拼多多真实拉单异常。"""


@dataclass(frozen=True)
class PddRealPullParams:
    store_id: int
    start_confirm_at: Optional[str] = None
    end_confirm_at: Optional[str] = None
    order_status: int = DEFAULT_PDD_ORDER_STATUS
    page: int = DEFAULT_PDD_PAGE
    page_size: int = DEFAULT_PDD_PAGE_SIZE


class PddRealPullService:
    """
    PDD 真实拉单第一版。

    当前阶段职责：
    - 使用当前店铺 access_token 调用 pdd.order.list.get
    - 以成交时间窗口拉取待发货订单
    - 返回最小订单摘要
    - 不做 OMS ingest
    """

    async def fetch_order_page(
        self,
        *,
        session: AsyncSession,
        params: PddRealPullParams,
    ) -> PddOrderPageResult:
        if params.store_id <= 0:
            raise PddRealPullServiceError("store_id must be positive")

        if params.page <= 0:
            raise PddRealPullServiceError("page must be positive")

        if params.page_size <= 0:
            raise PddRealPullServiceError("page_size must be positive")

        if params.page_size > MAX_PDD_PAGE_SIZE:
            raise PddRealPullServiceError(
                f"page_size must be <= {MAX_PDD_PAGE_SIZE}"
            )

        if params.order_status <= 0:
            raise PddRealPullServiceError("order_status must be positive")

        start_text, end_text = self._resolve_time_window(
            start_confirm_at=params.start_confirm_at,
            end_confirm_at=params.end_confirm_at,
        )

        app_config = await require_enabled_pdd_app_config(session)
        config = build_pdd_open_config_from_model(app_config)

        credential = await get_credential_by_store_platform(
            session,
            store_id=params.store_id,
            platform=PDD_PLATFORM,
        )
        if credential is None:
            raise PddRealPullServiceError("pdd credential not found")

        if credential.expires_at <= datetime.now(timezone.utc):
            raise PddRealPullServiceError("pdd credential expired")

        request = PddOrderListRequest(
            start_confirm_at=start_text,
            end_confirm_at=end_text,
            order_status=params.order_status,
            page=params.page,
            page_size=params.page_size,
        )

        client = PddOpenClient(config=config)
        try:
            payload = await client.post(
                api_type=PDD_ORDER_LIST_API_TYPE,
                business_params={
                    **request.to_business_params(),
                    "access_token": credential.access_token,
                },
            )
        except PddOpenClientError as exc:
            raise PddRealPullServiceError(f"pdd order list request failed: {exc}") from exc

        orders, has_more = self._parse_order_page(payload)

        return PddOrderPageResult(
            page=params.page,
            page_size=params.page_size,
            orders_count=len(orders),
            has_more=has_more,
            orders=orders,
            raw_payload=payload,
            start_confirm_at=start_text,
            end_confirm_at=end_text,
        )

    def _resolve_time_window(
        self,
        *,
        start_confirm_at: Optional[str],
        end_confirm_at: Optional[str],
    ) -> tuple[str, str]:
        now = datetime.now(timezone.utc)

        if not end_confirm_at and not start_confirm_at:
            end_dt = now
            start_dt = end_dt - timedelta(
                minutes=DEFAULT_PDD_WINDOW_MINUTES,
                seconds=DEFAULT_PDD_SAFETY_BUFFER_SECONDS,
            )
            return self._format_dt(end_dt=start_dt), self._format_dt(end_dt=end_dt)

        if not start_confirm_at or not end_confirm_at:
            raise PddRealPullServiceError(
                "start_confirm_at and end_confirm_at must be both provided"
            )

        start_dt = self._parse_dt(start_confirm_at)
        end_dt = self._parse_dt(end_confirm_at)

        if end_dt <= start_dt:
            raise PddRealPullServiceError("end_confirm_at must be greater than start_confirm_at")

        if (end_dt - start_dt) > timedelta(hours=MAX_PDD_WINDOW_HOURS):
            raise PddRealPullServiceError("time window must be <= 24 hours")

        safe_start_dt = start_dt - timedelta(seconds=DEFAULT_PDD_SAFETY_BUFFER_SECONDS)
        return self._format_dt(end_dt=safe_start_dt), self._format_dt(end_dt=end_dt)

    def _parse_order_page(
        self,
        payload: Dict[str, Any],
    ) -> tuple[List[PddOrderSummary], bool]:
        # 尽量兼容不同返回包装层；真正字段以联调结果为准逐步收紧
        candidates = [
            payload.get("order_list_get_response"),
            payload.get("pdd_order_list_get_response"),
            payload.get("order_list_response"),
            payload,
        ]

        response_obj: Dict[str, Any] = {}
        for item in candidates:
            if isinstance(item, dict):
                response_obj = item
                break

        orders_raw = self._extract_orders_list(response_obj)

        summaries: List[PddOrderSummary] = []
        for order in orders_raw:
            if not isinstance(order, dict):
                continue

            platform_order_id = self._first_non_empty_str(
                order,
                "order_sn",
                "order_no",
                "order_id",
            )
            if not platform_order_id:
                continue

            receiver_name = self._first_non_empty_str(
                order,
                "receiver_name",
                "receive_name",
                "consignee",
            )
            receiver_phone = self._first_non_empty_str(
                order,
                "receiver_phone",
                "receiver_mobile",
                "mobile",
                "phone",
            )
            receiver_address = self._build_address_summary(order)
            buyer_memo = self._first_non_empty_str(
                order,
                "buyer_memo",
                "memo",
                "remark",
            )
            confirm_at = self._first_non_empty_str(
                order,
                "confirm_time",
                "confirm_at",
                "pay_time",
            )

            items_count = self._extract_items_count(order)

            order_status = None
            raw_status = order.get("order_status")
            if raw_status is not None:
                try:
                    order_status = int(raw_status)
                except (TypeError, ValueError):
                    order_status = None

            summaries.append(
                PddOrderSummary(
                    platform_order_id=platform_order_id,
                    order_status=order_status,
                    confirm_at=confirm_at,
                    receiver_name_masked=receiver_name,
                    receiver_phone_masked=receiver_phone,
                    receiver_address_summary_masked=receiver_address,
                    buyer_memo=buyer_memo,
                    items_count=items_count,
                    raw_order=order,
                )
            )

        has_more = self._extract_has_more(response_obj, len(summaries))
        return summaries, has_more

    def _extract_orders_list(self, response_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates = [
            response_obj.get("order_list"),
            response_obj.get("orders"),
            response_obj.get("order_list_get_response"),
            response_obj.get("order_info_list"),
        ]
        for item in candidates:
            if isinstance(item, list):
                return [x for x in item if isinstance(x, dict)]
            if isinstance(item, dict):
                for key in ("order_list", "orders", "order_info_list"):
                    nested = item.get(key)
                    if isinstance(nested, list):
                        return [x for x in nested if isinstance(x, dict)]
        return []

    def _extract_items_count(self, order: Dict[str, Any]) -> int:
        for key in ("item_list", "order_item_list", "goods_list"):
            items = order.get(key)
            if isinstance(items, list):
                return len(items)

        for key in ("goods_count", "item_count"):
            raw = order.get(key)
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue

        return 0

    def _extract_has_more(self, response_obj: Dict[str, Any], count: int) -> bool:
        for key in ("has_next_page", "has_more"):
            raw = response_obj.get(key)
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, int):
                return raw != 0

        # 没有明确标记时，保守策略：满页视为可能还有下一页
        return count >= DEFAULT_PDD_PAGE_SIZE

    def _build_address_summary(self, order: Dict[str, Any]) -> Optional[str]:
        parts = [
            self._first_non_empty_str(order, "province", "receiver_province"),
            self._first_non_empty_str(order, "city", "receiver_city"),
            self._first_non_empty_str(order, "town", "district", "receiver_district"),
            self._first_non_empty_str(order, "address", "receiver_address", "detail_address"),
        ]
        merged = "".join([part for part in parts if part])
        return merged or None

    def _parse_dt(self, value: str) -> datetime:
        text = str(value or "").strip()
        if not text:
            raise PddRealPullServiceError("time value is required")

        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise PddRealPullServiceError(
                f"invalid datetime format: {text!r}, expected yyyy-MM-dd HH:mm:ss"
            ) from exc

        return dt.replace(tzinfo=timezone.utc)

    def _format_dt(self, *, end_dt: datetime) -> str:
        return end_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _first_non_empty_str(self, data: Dict[str, Any], *keys: str) -> Optional[str]:
        for key in keys:
            value = str(data.get(key) or "").strip()
            if value:
                return value
        return None
