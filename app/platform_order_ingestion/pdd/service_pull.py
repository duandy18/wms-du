# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/pdd/service_pull.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .access_repository import (
    ConnectionUpsertInput,
    get_connection_by_store_platform,
    get_credential_by_store_platform,
    upsert_connection_by_store_platform,
)
from .contracts import PddOrderSummary
from .repository import get_enabled_pdd_app_config
from .service_real_pull import (
    PddRealPullParams,
    PddRealPullService,
    PddRealPullServiceError,
)
from .settings import PddOpenConfigError, build_pdd_open_config_from_model


PDD_PLATFORM = "pdd"


class PddPullServiceError(Exception):
    """OMS 拼多多 test-pull 服务异常。"""


@dataclass(frozen=True)
class PddPullCheckResult:
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
    page: int = 1
    page_size: int = 50
    has_more: bool = False
    orders: list[PddOrderSummary] = field(default_factory=list)
    start_confirm_at: str | None = None
    end_confirm_at: str | None = None


class PddPullService:
    """
    OMS / 拼多多 test-pull 服务。

    当前阶段职责：
    - 检查系统级 app-config 是否可用
    - 检查当前店铺 credential 是否存在、是否过期
    - 推进 store_platform_connections 状态
    - 前置校验通过后，真实拉取一页订单摘要
    - 不执行 OMS ingest
    """

    def __init__(self) -> None:
        pass

    async def check_pull_ready(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        start_confirm_at: str | None = None,
        end_confirm_at: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PddPullCheckResult:
        if store_id <= 0:
            raise PddPullServiceError("store_id must be positive")

        now = datetime.now(timezone.utc)

        app_config = await get_enabled_pdd_app_config(session)
        if app_config is None:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=PDD_PLATFORM,
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
                platform=PDD_PLATFORM,
            )
            return self._to_result(store_id=store_id, row=row)

        try:
            build_pdd_open_config_from_model(app_config)
        except PddOpenConfigError:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=PDD_PLATFORM,
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
                platform=PDD_PLATFORM,
            )
            return self._to_result(store_id=store_id, row=row)

        credential = await get_credential_by_store_platform(
            session,
            store_id=store_id,
            platform=PDD_PLATFORM,
        )

        if credential is None:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=PDD_PLATFORM,
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
                platform=PDD_PLATFORM,
            )
            return self._to_result(store_id=store_id, row=row)

        expires_at = credential.expires_at
        expired = expires_at <= now

        if expired:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=PDD_PLATFORM,
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
                platform=PDD_PLATFORM,
            )
            return self._to_result(store_id=store_id, row=row)

        real_pull_service = PddRealPullService()

        try:
            page_result = await real_pull_service.fetch_order_page(
                session=session,
                params=PddRealPullParams(
                    store_id=store_id,
                    start_confirm_at=start_confirm_at,
                    end_confirm_at=end_confirm_at,
                    order_status=1,
                    page=page,
                    page_size=page_size,
                ),
            )
        except PddRealPullServiceError:
            await upsert_connection_by_store_platform(
                session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=PDD_PLATFORM,
                    auth_source="oauth",
                    connection_status="connected",
                    credential_status="valid",
                    reauth_required=False,
                    pull_ready=False,
                    status="ready",
                    status_reason="real_pull_not_implemented",
                    last_pull_checked_at=now,
                    last_error_at=now,
                ),
            )
            row = await get_connection_by_store_platform(
                session,
                store_id=store_id,
                platform=PDD_PLATFORM,
            )
            return self._to_result(
                store_id=store_id,
                row=row,
                orders_count=0,
                page=page,
                page_size=page_size,
                has_more=False,
                orders=[],
                start_confirm_at=start_confirm_at,
                end_confirm_at=end_confirm_at,
            )

        status_reason = "real_pull_empty" if page_result.orders_count == 0 else "real_pull_ok"

        await upsert_connection_by_store_platform(
            session,
            data=ConnectionUpsertInput(
                store_id=store_id,
                platform=PDD_PLATFORM,
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
            platform=PDD_PLATFORM,
        )
        return self._to_result(
            store_id=store_id,
            row=row,
            orders_count=page_result.orders_count,
            page=page_result.page,
            page_size=page_result.page_size,
            has_more=page_result.has_more,
            orders=page_result.orders,
            start_confirm_at=page_result.start_confirm_at,
            end_confirm_at=page_result.end_confirm_at,
        )

    def _to_result(
        self,
        *,
        store_id: int,
        row,
        orders_count: int = 0,
        page: int = 1,
        page_size: int = 50,
        has_more: bool = False,
        orders: list[PddOrderSummary] | None = None,
        start_confirm_at: str | None = None,
        end_confirm_at: str | None = None,
    ) -> PddPullCheckResult:
        if row is None:
            return PddPullCheckResult(
                platform=PDD_PLATFORM,
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
                page=page,
                page_size=page_size,
                has_more=has_more,
                orders=orders or [],
                start_confirm_at=start_confirm_at,
                end_confirm_at=end_confirm_at,
            )

        return PddPullCheckResult(
            platform=PDD_PLATFORM,
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
            page=page,
            page_size=page_size,
            has_more=has_more,
            orders=orders or [],
            start_confirm_at=start_confirm_at,
            end_confirm_at=end_confirm_at,
        )
