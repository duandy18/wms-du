# app/oms/platforms/jd/service_pull.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import (
    ConnectionUpsertInput,
    get_connection_by_store_platform,
    get_credential_by_store_platform,
    get_enabled_jd_app_config,
    upsert_connection_by_store_platform,
)
from .service_order_detail import (
    JdOrderDetail,
    JdOrderDetailService,
    JdOrderDetailServiceError,
)
from .service_real_pull import (
    JD_PLATFORM,
    JdOrderSummary,
    JdRealPullParams,
    JdRealPullService,
    JdRealPullServiceError,
)
from .settings import JdJosConfigError, build_jd_jos_config_from_model


class JdPullServiceError(Exception):
    """OMS 京东 test-pull 服务异常。"""


@dataclass(frozen=True)
class JdPullOrderResult:
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
    detail_loaded: bool = False
    detail: JdOrderDetail | None = None


@dataclass(frozen=True)
class JdPullCheckResult:
    platform: str
    store_id: int
    auth_source: str
    connection_status: str
    credential_status: str
    reauth_required: bool
    pull_ready: bool
    status: str
    status_reason: str
    last_authorized_at: str | None
    last_pull_checked_at: str | None
    last_error_at: str | None
    orders_count: int = 0
    detailed_orders_count: int = 0
    page: int = 1
    page_size: int = 20
    has_more: bool = False
    start_time: str | None = None
    end_time: str | None = None
    orders: list[JdPullOrderResult] = field(default_factory=list)


class JdPullService:
    """
    OMS / 京东 test-pull 服务。

    当前阶段职责：
    - 检查系统级 app-config 是否可用
    - 检查当前店铺 credential 是否存在、是否过期
    - 推进 store_platform_connections 状态
    - 前置校验通过后，真实拉取一页订单摘要
    - 逐单补详情，返回最小测试结果
    - 不执行 OMS ingest
    - 不做事实表入库
    """

    async def check_pull_ready(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        start_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        page_size: int = 20,
        order_state: str | None = None,
    ) -> JdPullCheckResult:
        if store_id <= 0:
            raise JdPullServiceError("store_id must be positive")

        now = datetime.now(timezone.utc)

        app_config = await get_enabled_jd_app_config(session)
        if app_config is None:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=JD_PLATFORM,
                    auth_source="none",
                    connection_status="not_connected",
                    credential_status="missing",
                    reauth_required=False,
                    pull_ready=False,
                    status="not_ready",
                    status_reason="platform_app_not_ready",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            row = await get_connection_by_store_platform(
                session,
                store_id=store_id,
                platform=JD_PLATFORM,
            )
            return self._to_result(store_id=store_id, row=row)

        try:
            build_jd_jos_config_from_model(app_config)
        except JdJosConfigError:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=JD_PLATFORM,
                    auth_source="none",
                    connection_status="not_connected",
                    credential_status="missing",
                    reauth_required=False,
                    pull_ready=False,
                    status="not_ready",
                    status_reason="platform_app_not_ready",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            row = await get_connection_by_store_platform(
                session,
                store_id=store_id,
                platform=JD_PLATFORM,
            )
            return self._to_result(store_id=store_id, row=row)

        credential = await get_credential_by_store_platform(
            session,
            store_id=store_id,
            platform=JD_PLATFORM,
        )
        if credential is None:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=JD_PLATFORM,
                    auth_source="none",
                    connection_status="not_connected",
                    credential_status="missing",
                    reauth_required=False,
                    pull_ready=False,
                    status="not_ready",
                    status_reason="credential_missing",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            row = await get_connection_by_store_platform(
                session,
                store_id=store_id,
                platform=JD_PLATFORM,
            )
            return self._to_result(store_id=store_id, row=row)

        if credential.expires_at <= now:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=JD_PLATFORM,
                    auth_source="oauth",
                    connection_status="connected",
                    credential_status="expired",
                    reauth_required=True,
                    pull_ready=False,
                    status="not_ready",
                    status_reason="credential_expired",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            row = await get_connection_by_store_platform(
                session,
                store_id=store_id,
                platform=JD_PLATFORM,
            )
            return self._to_result(store_id=store_id, row=row)

        real_pull_service = JdRealPullService()

        try:
            page_result = await real_pull_service.fetch_order_page(
                session=session,
                params=JdRealPullParams(
                    store_id=store_id,
                    start_time=start_time,
                    end_time=end_time,
                    page=page,
                    page_size=page_size,
                    order_state=order_state,
                ),
            )
        except JdRealPullServiceError:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=JD_PLATFORM,
                    auth_source="oauth",
                    connection_status="connected",
                    credential_status="valid",
                    reauth_required=False,
                    pull_ready=False,
                    status="not_ready",
                    status_reason="real_pull_failed",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            row = await get_connection_by_store_platform(
                session,
                store_id=store_id,
                platform=JD_PLATFORM,
            )
            return self._to_result(
                store_id=store_id,
                row=row,
                orders_count=0,
                detailed_orders_count=0,
                page=page,
                page_size=page_size,
                has_more=False,
                orders=[],
                start_time=start_time,
                end_time=end_time,
            )

        detail_service = JdOrderDetailService()
        orders: list[JdPullOrderResult] = []
        detailed_orders_count = 0

        for summary in page_result.orders:
            detail_loaded = False
            detail: JdOrderDetail | None = None

            try:
                detail = await detail_service.fetch_order_detail(
                    session=session,
                    store_id=store_id,
                    order_id=summary.platform_order_id,
                )
                detail_loaded = True
                detailed_orders_count += 1
            except JdOrderDetailServiceError:
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
            session,
            data=ConnectionUpsertInput(
                store_id=store_id,
                platform=JD_PLATFORM,
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
        row = await get_connection_by_store_platform(
            session,
            store_id=store_id,
            platform=JD_PLATFORM,
        )
        return self._to_result(
            store_id=store_id,
            row=row,
            orders_count=page_result.orders_count,
            detailed_orders_count=detailed_orders_count,
            page=page_result.page,
            page_size=page_result.page_size,
            has_more=page_result.has_more,
            orders=orders,
            start_time=page_result.start_time,
            end_time=page_result.end_time,
        )

    def _merge_summary_and_detail(
        self,
        *,
        summary: JdOrderSummary,
        detail_loaded: bool,
        detail: JdOrderDetail | None,
    ) -> JdPullOrderResult:
        detail_items_count = len(detail.items or []) if detail else 0
        return JdPullOrderResult(
            platform_order_id=summary.platform_order_id,
            order_state=detail.order_state if detail and detail.order_state else summary.order_state,
            order_type=detail.order_type if detail and detail.order_type else summary.order_type,
            order_start_time=detail.order_start_time if detail and detail.order_start_time else summary.order_start_time,
            modified=detail.modified if detail and detail.modified else summary.modified,
            consignee_name_masked=detail.consignee_name if detail and detail.consignee_name else summary.consignee_name_masked,
            consignee_mobile_masked=detail.consignee_mobile if detail and detail.consignee_mobile else summary.consignee_mobile_masked,
            consignee_address_summary_masked=detail.consignee_address if detail and detail.consignee_address else summary.consignee_address_summary_masked,
            order_remark=detail.order_remark if detail and detail.order_remark else summary.order_remark,
            order_total_price=detail.order_total_price if detail and detail.order_total_price else summary.order_total_price,
            items_count=detail_items_count if detail_loaded else summary.items_count,
            detail_loaded=detail_loaded,
            detail=detail,
        )

    def _to_result(
        self,
        *,
        store_id: int,
        row,
        orders_count: int = 0,
        detailed_orders_count: int = 0,
        page: int = 1,
        page_size: int = 20,
        has_more: bool = False,
        orders: list[JdPullOrderResult] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> JdPullCheckResult:
        if row is None:
            return JdPullCheckResult(
                platform=JD_PLATFORM,
                store_id=store_id,
                auth_source="none",
                connection_status="not_connected",
                credential_status="missing",
                reauth_required=False,
                pull_ready=False,
                status="not_connected",
                status_reason="authorization_missing",
                last_authorized_at=None,
                last_pull_checked_at=None,
                last_error_at=None,
                orders_count=orders_count,
                detailed_orders_count=detailed_orders_count,
                page=page,
                page_size=page_size,
                has_more=has_more,
                start_time=start_time,
                end_time=end_time,
                orders=orders or [],
            )

        return JdPullCheckResult(
            platform=JD_PLATFORM,
            store_id=store_id,
            auth_source=row.auth_source,
            connection_status=row.connection_status,
            credential_status=row.credential_status,
            reauth_required=bool(row.reauth_required),
            pull_ready=bool(row.pull_ready),
            status=row.status,
            status_reason=row.status_reason or "",
            last_authorized_at=row.last_authorized_at.isoformat()
            if row.last_authorized_at
            else None,
            last_pull_checked_at=row.last_pull_checked_at.isoformat()
            if row.last_pull_checked_at
            else None,
            last_error_at=row.last_error_at.isoformat()
            if row.last_error_at
            else None,
            orders_count=orders_count,
            detailed_orders_count=detailed_orders_count,
            page=page,
            page_size=page_size,
            has_more=has_more,
            start_time=start_time,
            end_time=end_time,
            orders=orders or [],
        )
