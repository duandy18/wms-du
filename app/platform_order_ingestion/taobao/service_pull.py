# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/taobao/service_pull.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import (
    ConnectionUpsertInput,
    get_credential_by_store_platform,
    upsert_connection_by_store_platform,
)
from .service_order_detail import (
    TaobaoOrderDetail,
    TaobaoOrderDetailService,
    TaobaoOrderDetailServiceError,
)
from .service_real_pull import (
    TAOBAO_PLATFORM,
    TaobaoOrderSummary,
    TaobaoRealPullParams,
    TaobaoRealPullService,
    TaobaoRealPullServiceError,
)
from .settings import TaobaoTopConfig


class TaobaoPullServiceError(Exception):
    """OMS 淘宝 test-pull 服务异常。"""


@dataclass(frozen=True)
class TaobaoPullOrderResult:
    tid: str
    status: str | None = None
    type: str | None = None
    created: str | None = None
    pay_time: str | None = None
    modified: str | None = None
    receiver_name: str | None = None
    receiver_mobile: str | None = None
    receiver_address_summary: str | None = None
    payment: str | None = None
    total_fee: str | None = None
    items_count: int = 0
    detail_loaded: bool = False
    detail: TaobaoOrderDetail | None = None


@dataclass(frozen=True)
class TaobaoPullCheckResult:
    store_id: int
    platform: str
    executed_real_pull: bool
    pull_ready: bool
    status: str
    status_reason: Optional[str]
    orders_count: int = 0
    detailed_orders_count: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False
    start_time: str | None = None
    end_time: str | None = None
    orders: list[TaobaoPullOrderResult] = field(default_factory=list)


class TaobaoPullService:
    """
    OMS / 淘宝 test-pull 服务。

    职责：
    - 校验是否具备真实拉单前提；
    - allow_real_request=False 时只更新连接状态，不发真实请求；
    - allow_real_request=True 时拉取一页淘宝订单摘要并逐单补详情；
    - 推进 store_platform_connections 状态。

    不负责：
    - 写 taobao_orders / taobao_order_items；
    - 写 platform_order_lines；
    - FSKU / SKU 映射；
    - 内部订单创建。
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        config: Optional[TaobaoTopConfig],
    ) -> None:
        self.session = session
        self.config = config

    async def check_pull_ready(
        self,
        *,
        store_id: int,
        allow_real_request: bool = False,
        start_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
    ) -> TaobaoPullCheckResult:
        if store_id <= 0:
            raise TaobaoPullServiceError("store_id must be > 0")

        now = datetime.now(timezone.utc)
        platform = TAOBAO_PLATFORM

        if self.config is None:
            await upsert_connection_by_store_platform(
                self.session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=platform,
                    auth_source="none",
                    connection_status="not_connected",
                    credential_status="missing",
                    reauth_required=False,
                    pull_ready=False,
                    status="error",
                    status_reason="platform_app_not_ready",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            await self.session.commit()
            return self._to_result(
                store_id=store_id,
                executed_real_pull=False,
                pull_ready=False,
                status="error",
                status_reason="platform_app_not_ready",
                page=page,
                page_size=page_size,
                start_time=start_time,
                end_time=end_time,
            )

        credential = await get_credential_by_store_platform(
            self.session,
            store_id=store_id,
            platform=platform,
        )
        if credential is None:
            await upsert_connection_by_store_platform(
                self.session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=platform,
                    auth_source="none",
                    connection_status="not_connected",
                    credential_status="missing",
                    reauth_required=False,
                    pull_ready=False,
                    status="auth_pending",
                    status_reason="credential_missing",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            await self.session.commit()
            return self._to_result(
                store_id=store_id,
                executed_real_pull=False,
                pull_ready=False,
                status="auth_pending",
                status_reason="credential_missing",
                page=page,
                page_size=page_size,
                start_time=start_time,
                end_time=end_time,
            )

        if credential.expires_at <= now:
            await upsert_connection_by_store_platform(
                self.session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=platform,
                    auth_source="oauth",
                    connection_status="connected",
                    credential_status="expired",
                    reauth_required=True,
                    pull_ready=False,
                    status="auth_pending",
                    status_reason="credential_expired",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            await self.session.commit()
            return self._to_result(
                store_id=store_id,
                executed_real_pull=False,
                pull_ready=False,
                status="auth_pending",
                status_reason="credential_expired",
                page=page,
                page_size=page_size,
                start_time=start_time,
                end_time=end_time,
            )

        if not allow_real_request:
            await upsert_connection_by_store_platform(
                self.session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=platform,
                    auth_source="oauth",
                    connection_status="connected",
                    credential_status="valid",
                    reauth_required=False,
                    pull_ready=False,
                    status="error",
                    status_reason="real_pull_disabled",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            await self.session.commit()
            return self._to_result(
                store_id=store_id,
                executed_real_pull=False,
                pull_ready=False,
                status="error",
                status_reason="real_pull_disabled",
                page=page,
                page_size=page_size,
                start_time=start_time,
                end_time=end_time,
            )

        real_pull_service = TaobaoRealPullService()
        try:
            page_result = await real_pull_service.fetch_order_page(
                session=self.session,
                params=TaobaoRealPullParams(
                    store_id=store_id,
                    start_time=start_time,
                    end_time=end_time,
                    status=status,
                    page=page,
                    page_size=page_size,
                ),
            )
        except TaobaoRealPullServiceError:
            await upsert_connection_by_store_platform(
                self.session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=platform,
                    auth_source="oauth",
                    connection_status="connected",
                    credential_status="valid",
                    reauth_required=False,
                    pull_ready=False,
                    status="error",
                    status_reason="real_pull_failed",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            await self.session.commit()
            return self._to_result(
                store_id=store_id,
                executed_real_pull=True,
                pull_ready=False,
                status="error",
                status_reason="real_pull_failed",
                page=page,
                page_size=page_size,
                start_time=start_time,
                end_time=end_time,
            )

        detail_service = TaobaoOrderDetailService()
        orders: list[TaobaoPullOrderResult] = []
        detailed_orders_count = 0

        for summary in page_result.orders:
            detail_loaded = False
            detail: TaobaoOrderDetail | None = None

            try:
                detail = await detail_service.fetch_order_detail(
                    session=self.session,
                    store_id=store_id,
                    tid=summary.tid,
                )
                detail_loaded = True
                detailed_orders_count += 1
            except TaobaoOrderDetailServiceError:
                detail_loaded = False
                detail = None

            orders.append(
                self._merge_summary_and_detail(
                    summary=summary,
                    detail_loaded=detail_loaded,
                    detail=detail,
                )
            )

        status_reason = "real_pull_empty" if page_result.orders_count == 0 else "real_pull_ok"

        await upsert_connection_by_store_platform(
            self.session,
            data=ConnectionUpsertInput(
                store_id=store_id,
                platform=platform,
                auth_source="oauth",
                connection_status="connected",
                credential_status="valid",
                reauth_required=False,
                pull_ready=True,
                status="ready",
                status_reason=status_reason,
                last_pull_checked_at=now,
            ),
        )
        await self.session.commit()

        return self._to_result(
            store_id=store_id,
            executed_real_pull=True,
            pull_ready=True,
            status="ready",
            status_reason=status_reason,
            orders_count=page_result.orders_count,
            detailed_orders_count=detailed_orders_count,
            page=page_result.page,
            page_size=page_result.page_size,
            has_more=page_result.has_more,
            start_time=page_result.start_time,
            end_time=page_result.end_time,
            orders=orders,
        )

    def _merge_summary_and_detail(
        self,
        *,
        summary: TaobaoOrderSummary,
        detail_loaded: bool,
        detail: TaobaoOrderDetail | None,
    ) -> TaobaoPullOrderResult:
        detail_items_count = len(detail.items or []) if detail else 0
        return TaobaoPullOrderResult(
            tid=summary.tid,
            status=detail.status if detail and detail.status else summary.status,
            type=detail.type if detail and detail.type else summary.type,
            created=detail.created if detail and detail.created else summary.created,
            pay_time=detail.pay_time if detail and detail.pay_time else summary.pay_time,
            modified=detail.modified if detail and detail.modified else summary.modified,
            receiver_name=detail.receiver_name if detail and detail.receiver_name else summary.receiver_name,
            receiver_mobile=detail.receiver_mobile if detail and detail.receiver_mobile else summary.receiver_mobile,
            receiver_address_summary=(
                detail.receiver_address
                if detail and detail.receiver_address
                else summary.receiver_address
            ),
            payment=detail.payment if detail and detail.payment else summary.payment,
            total_fee=detail.total_fee if detail and detail.total_fee else summary.total_fee,
            items_count=detail_items_count if detail_loaded else summary.items_count,
            detail_loaded=detail_loaded,
            detail=detail,
        )

    def _to_result(
        self,
        *,
        store_id: int,
        executed_real_pull: bool,
        pull_ready: bool,
        status: str,
        status_reason: str | None,
        orders_count: int = 0,
        detailed_orders_count: int = 0,
        page: int = 1,
        page_size: int = 50,
        has_more: bool = False,
        start_time: str | None = None,
        end_time: str | None = None,
        orders: list[TaobaoPullOrderResult] | None = None,
    ) -> TaobaoPullCheckResult:
        return TaobaoPullCheckResult(
            store_id=store_id,
            platform=TAOBAO_PLATFORM,
            executed_real_pull=executed_real_pull,
            pull_ready=pull_ready,
            status=status,
            status_reason=status_reason,
            orders_count=orders_count,
            detailed_orders_count=detailed_orders_count,
            page=page,
            page_size=page_size,
            has_more=has_more,
            start_time=start_time,
            end_time=end_time,
            orders=orders or [],
        )
