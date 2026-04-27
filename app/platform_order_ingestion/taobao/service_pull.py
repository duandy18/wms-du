# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/taobao/service_pull.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .repository import (
    ConnectionUpsertInput,
    get_credential_by_store_platform,
    upsert_connection_by_store_platform,
)
from .settings import TaobaoTopConfig


TAOBAO_PLATFORM = "taobao"


class TaobaoPullServiceError(Exception):
    """OMS 淘宝 test-pull 服务异常。"""


@dataclass(frozen=True)
class TaobaoPullCheckResult:
    store_id: int
    platform: str
    executed_real_pull: bool
    pull_ready: bool
    status: str
    status_reason: Optional[str]


class TaobaoPullService:
    """
    OMS / 淘宝 test-pull 服务。

    当前阶段职责：
    - 校验是否具备真实拉单前提
    - 推进 store_platform_connections 状态
    - 默认不发真实请求

    当前阶段不负责：
    - 真实订单读取接口调用
    - 真实拉单结果解析
    - 前端 contract 拼装
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
    ) -> TaobaoPullCheckResult:
        if store_id <= 0:
            raise TaobaoPullServiceError("store_id must be > 0")

        now = datetime.now(timezone.utc)
        platform = TAOBAO_PLATFORM

        # 1) 平台应用配置是否齐备
        if self.config is None:
            await upsert_connection_by_store_platform(
                self.session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=platform,
                    pull_ready=False,
                    status="error",
                    status_reason="platform_app_not_ready",
                    last_error_at=now,
                ),
            )
            await self.session.commit()
            return TaobaoPullCheckResult(
                store_id=store_id,
                platform=platform,
                executed_real_pull=False,
                pull_ready=False,
                status="error",
                status_reason="platform_app_not_ready",
            )

        # 2) credentials 是否存在
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
                    credential_status="missing",
                    reauth_required=False,
                    pull_ready=False,
                    status="auth_pending",
                    status_reason="credential_missing",
                    last_error_at=now,
                ),
            )
            await self.session.commit()
            return TaobaoPullCheckResult(
                store_id=store_id,
                platform=platform,
                executed_real_pull=False,
                pull_ready=False,
                status="auth_pending",
                status_reason="credential_missing",
            )

        # 3) credentials 是否过期
        if credential.expires_at <= now:
            await upsert_connection_by_store_platform(
                self.session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=platform,
                    credential_status="expired",
                    reauth_required=True,
                    pull_ready=False,
                    status="auth_pending",
                    status_reason="credential_expired",
                    last_error_at=now,
                ),
            )
            await self.session.commit()
            return TaobaoPullCheckResult(
                store_id=store_id,
                platform=platform,
                executed_real_pull=False,
                pull_ready=False,
                status="auth_pending",
                status_reason="credential_expired",
            )

        # 4) 当前阶段默认不发真实请求
        if not allow_real_request:
            await upsert_connection_by_store_platform(
                self.session,
                data=ConnectionUpsertInput(
                    store_id=store_id,
                    platform=platform,
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
            return TaobaoPullCheckResult(
                store_id=store_id,
                platform=platform,
                executed_real_pull=False,
                pull_ready=False,
                status="error",
                status_reason="real_pull_disabled",
            )

        # 5) 预留：未来真实订单相关最小读取接口验证
        # 当前先不实现真实调用，避免在未正式接入平台时伪造成功结果
        await upsert_connection_by_store_platform(
            self.session,
            data=ConnectionUpsertInput(
                store_id=store_id,
                platform=platform,
                credential_status="valid",
                reauth_required=False,
                pull_ready=False,
                status="error",
                status_reason="real_pull_not_implemented",
                last_pull_checked_at=now,
                last_error_at=now,
            ),
        )
        await self.session.commit()
        return TaobaoPullCheckResult(
            store_id=store_id,
            platform=platform,
            executed_real_pull=False,
            pull_ready=False,
            status="error",
            status_reason="real_pull_not_implemented",
        )
