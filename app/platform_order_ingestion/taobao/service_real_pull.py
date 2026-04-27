# Module split: Taobao platform order real-pull service.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

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
TAOBAO_TRADES_SOLD_GET_METHOD = "taobao.trades.sold.get"

DEFAULT_TAOBAO_PAGE = 1
DEFAULT_TAOBAO_PAGE_SIZE = 50
MAX_TAOBAO_PAGE_SIZE = 100
DEFAULT_TAOBAO_WINDOW_MINUTES = 30
DEFAULT_TAOBAO_SAFETY_BUFFER_SECONDS = 60
MAX_TAOBAO_WINDOW_DAYS = 30

TAOBAO_TRADE_SUMMARY_FIELDS = ",".join(
    [
        "tid",
        "status",
        "type",
        "buyer_nick",
        "buyer_open_uid",
        "created",
        "pay_time",
        "modified",
        "payment",
        "total_fee",
        "post_fee",
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
        "orders",
    ]
)


class TaobaoRealPullServiceError(Exception):
    """淘宝真实拉单异常。"""


@dataclass(frozen=True)
class TaobaoOrderSummary:
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
    created: str | None = None
    pay_time: str | None = None
    modified: str | None = None
    items_count: int = 0
    raw_order: dict[str, Any] | None = None


@dataclass(frozen=True)
class TaobaoOrderPageResult:
    page: int
    page_size: int
    orders_count: int
    has_more: bool
    start_time: str
    end_time: str
    orders: list[TaobaoOrderSummary]
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class TaobaoRealPullParams:
    store_id: int
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: Optional[str] = None
    page: int = DEFAULT_TAOBAO_PAGE
    page_size: int = DEFAULT_TAOBAO_PAGE_SIZE


class TaobaoRealPullService:
    """
    淘宝真实订单摘要拉取服务。

    职责：
    - 使用当前店铺 access_token 调用 taobao.trades.sold.get；
    - 按时间窗口拉取订单摘要；
    - 解析为平台原生摘要 DTO；
    - 不写 taobao_orders / taobao_order_items；
    - 不写 platform_order_lines；
    - 不做 FSKU / SKU 映射。
    """

    async def fetch_order_page(
        self,
        *,
        session: AsyncSession,
        params: TaobaoRealPullParams,
    ) -> TaobaoOrderPageResult:
        if params.store_id <= 0:
            raise TaobaoRealPullServiceError("store_id must be positive")
        if params.page <= 0:
            raise TaobaoRealPullServiceError("page must be positive")
        if params.page_size <= 0:
            raise TaobaoRealPullServiceError("page_size must be positive")
        if params.page_size > MAX_TAOBAO_PAGE_SIZE:
            raise TaobaoRealPullServiceError(f"page_size must be <= {MAX_TAOBAO_PAGE_SIZE}")

        start_text, end_text = self._resolve_time_window(
            start_time=params.start_time,
            end_time=params.end_time,
        )

        app_config = await require_enabled_taobao_app_config(session)
        config = build_taobao_top_config_from_model(app_config)

        credential = await get_credential_by_store_platform(
            session,
            store_id=params.store_id,
            platform=TAOBAO_PLATFORM,
        )
        if credential is None:
            raise TaobaoRealPullServiceError("taobao credential not found")
        if credential.expires_at <= datetime.now(timezone.utc):
            raise TaobaoRealPullServiceError("taobao credential expired")

        request = TaobaoTopRequest(
            method=TAOBAO_TRADES_SOLD_GET_METHOD,
            session=credential.access_token,
            biz_params=self._build_trades_sold_params(
                start_time=start_text,
                end_time=end_text,
                status=params.status,
                page=params.page,
                page_size=params.page_size,
            ),
        )

        client = TaobaoTopClient(config=config)
        try:
            response = await client.call(request)
        except TaobaoTopError as exc:
            raise TaobaoRealPullServiceError(f"taobao trades sold request failed: {exc}") from exc

        orders, has_more = self._parse_order_page(
            response.body,
            page=params.page,
            page_size=params.page_size,
        )

        return TaobaoOrderPageResult(
            page=int(params.page),
            page_size=int(params.page_size),
            orders_count=len(orders),
            has_more=bool(has_more),
            start_time=start_text,
            end_time=end_text,
            orders=orders,
            raw_payload=response.raw,
        )

    def _build_trades_sold_params(
        self,
        *,
        start_time: str,
        end_time: str,
        status: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "fields": TAOBAO_TRADE_SUMMARY_FIELDS,
            "start_created": start_time,
            "end_created": end_time,
            "page_no": int(page),
            "page_size": int(page_size),
            "use_has_next": True,
        }
        if status:
            payload["status"] = str(status).strip()
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
                minutes=DEFAULT_TAOBAO_WINDOW_MINUTES,
                seconds=DEFAULT_TAOBAO_SAFETY_BUFFER_SECONDS,
            )
            return self._format_dt(start_dt), self._format_dt(end_dt)

        if not start_time or not end_time:
            raise TaobaoRealPullServiceError("start_time and end_time must be both provided")

        start_dt = self._parse_dt(start_time)
        end_dt = self._parse_dt(end_time)

        if end_dt <= start_dt:
            raise TaobaoRealPullServiceError("end_time must be greater than start_time")
        if (end_dt - start_dt) > timedelta(days=MAX_TAOBAO_WINDOW_DAYS):
            raise TaobaoRealPullServiceError("time window must be <= 30 days")

        safe_start_dt = start_dt - timedelta(seconds=DEFAULT_TAOBAO_SAFETY_BUFFER_SECONDS)
        return self._format_dt(safe_start_dt), self._format_dt(end_dt)

    def _parse_order_page(
        self,
        body: Mapping[str, Any],
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[TaobaoOrderSummary], bool]:
        trades_raw = self._extract_trades_list(body)
        orders: list[TaobaoOrderSummary] = []

        for trade in trades_raw:
            if not isinstance(trade, Mapping):
                continue

            tid = self._first_non_empty_str(trade, "tid", "trade_id")
            if not tid:
                continue

            seller_flag = self._optional_int(trade.get("seller_flag"))
            orders.append(
                TaobaoOrderSummary(
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
                    seller_flag=seller_flag,
                    payment=self._money_text(trade.get("payment")),
                    total_fee=self._money_text(trade.get("total_fee")),
                    post_fee=self._money_text(trade.get("post_fee")),
                    created=self._first_non_empty_str(trade, "created"),
                    pay_time=self._first_non_empty_str(trade, "pay_time"),
                    modified=self._first_non_empty_str(trade, "modified"),
                    items_count=self._extract_items_count(trade),
                    raw_order=dict(trade),
                )
            )

        return orders, self._extract_has_more(body, count=len(orders), page=page, page_size=page_size)

    def _extract_trades_list(self, body: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        candidates: list[Any] = [
            body.get("trades"),
            body.get("trade"),
            body.get("trade_list"),
        ]
        for item in candidates:
            if isinstance(item, list):
                return [x for x in item if isinstance(x, Mapping)]
            if isinstance(item, Mapping):
                for key in ("trade", "trades", "trade_list"):
                    nested = item.get(key)
                    if isinstance(nested, list):
                        return [x for x in nested if isinstance(x, Mapping)]
        return []

    def _extract_items_count(self, trade: Mapping[str, Any]) -> int:
        orders = trade.get("orders")
        if isinstance(orders, list):
            return len(orders)
        if isinstance(orders, Mapping):
            nested = orders.get("order")
            if isinstance(nested, list):
                return len(nested)
        return 0

    def _extract_has_more(
        self,
        body: Mapping[str, Any],
        *,
        count: int,
        page: int,
        page_size: int,
    ) -> bool:
        for key in ("has_next", "has_more", "has_next_page"):
            raw = body.get(key)
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, int):
                return raw != 0
            if isinstance(raw, str):
                text = raw.strip().lower()
                if text in {"true", "1", "yes"}:
                    return True
                if text in {"false", "0", "no"}:
                    return False

        total = body.get("total_results") or body.get("total")
        try:
            if total is not None:
                return int(total) > int(page) * int(page_size)
        except (TypeError, ValueError):
            pass

        return count >= page_size

    def _parse_dt(self, value: str) -> datetime:
        text = str(value or "").strip()
        if not text:
            raise TaobaoRealPullServiceError("time value is required")
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise TaobaoRealPullServiceError(
                f"invalid datetime format: {text!r}, expected yyyy-MM-dd HH:mm:ss"
            ) from exc
        return dt.replace(tzinfo=timezone.utc)

    def _format_dt(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

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
