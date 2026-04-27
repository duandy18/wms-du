# Module split: platform order ingestion store-level status service.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_order_ingestion.repos.status import (
    count_enabled_app_configs,
    load_connection_row,
    load_credential_row,
    load_latest_job_with_run,
    load_store_row,
    normalize_platform,
)

_SUPPORTED_PLATFORMS = {"pdd", "taobao", "jd"}


class PlatformOrderIngestionStatusServiceError(Exception):
    """平台订单采集状态服务异常。"""


class PlatformOrderIngestionStoreNotFoundError(PlatformOrderIngestionStatusServiceError):
    """店铺不存在。"""


class PlatformOrderIngestionStatusService:
    async def get_store_status(
        self,
        session: AsyncSession,
        *,
        store_id: int,
    ) -> dict[str, Any]:
        store = await load_store_row(session, store_id=store_id)
        if store is None:
            raise PlatformOrderIngestionStoreNotFoundError(f"store not found: {store_id}")

        platform = normalize_platform(str(store["platform"]))
        app_enabled_count = await count_enabled_app_configs(session, platform=platform)
        credential = await load_credential_row(session, store_id=store_id, platform=platform)
        connection = await load_connection_row(session, store_id=store_id, platform=platform)
        latest_job = await load_latest_job_with_run(session, store_id=store_id, platform=platform)

        app_status = self._app_status(platform=platform, enabled_count=app_enabled_count)
        credential_status = self._credential_status(credential)
        connection_out = self._connection_out(connection)
        pull_ready = self._compute_pull_ready(
            store_active=bool(store["active"]),
            platform=platform,
            app_status=app_status,
            credential_status=credential_status["credential_status"],
            connection_pull_ready=bool(connection_out["pull_ready"]),
        )
        blocked_reasons = self._blocked_reasons(
            store_active=bool(store["active"]),
            platform=platform,
            app_status=app_status,
            credential_status=credential_status["credential_status"],
            connection_out=connection_out,
        )

        return {
            "platform": platform,
            "store": {
                "id": int(store["id"]),
                "platform": platform,
                "store_code": str(store["store_code"]),
                "store_name": str(store["store_name"]),
                "active": bool(store["active"]),
            },
            "app": {
                "configured": app_status == "ready",
                "enabled_count": app_enabled_count,
                "status": app_status,
            },
            "credential": credential_status,
            "connection": connection_out,
            "latest_job": self._latest_job_out(latest_job),
            "pull_ready": pull_ready,
            "blocked_reasons": blocked_reasons,
            "meta": {
                "source": "platform_order_ingestion_store_status",
            },
        }

    def _app_status(self, *, platform: str, enabled_count: int) -> str:
        if platform not in _SUPPORTED_PLATFORMS:
            return "unsupported_platform"
        if enabled_count <= 0:
            return "not_configured"
        if enabled_count > 1:
            return "ambiguous"
        return "ready"

    def _credential_status(self, row: Mapping | None) -> dict[str, Any]:
        if row is None:
            return {
                "present": False,
                "credential_type": None,
                "credential_status": "missing",
                "expires_at": None,
                "expired": False,
                "scope": None,
                "granted_identity_type": None,
                "granted_identity_value": None,
                "granted_identity_display": None,
            }

        expires_at = row["expires_at"]
        expired = bool(expires_at and expires_at <= datetime.now(timezone.utc))
        return {
            "present": True,
            "credential_type": row["credential_type"],
            "credential_status": "expired" if expired else "valid",
            "expires_at": self._dt(expires_at),
            "expired": expired,
            "scope": row["scope"],
            "granted_identity_type": row["granted_identity_type"],
            "granted_identity_value": row["granted_identity_value"],
            "granted_identity_display": row["granted_identity_display"],
        }

    def _connection_out(self, row: Mapping | None) -> dict[str, Any]:
        if row is None:
            return {
                "present": False,
                "auth_source": "none",
                "connection_status": "not_connected",
                "credential_status": "missing",
                "reauth_required": False,
                "pull_ready": False,
                "status": "not_connected",
                "status_reason": "authorization_missing",
                "last_authorized_at": None,
                "last_pull_checked_at": None,
                "last_error_at": None,
            }

        return {
            "present": True,
            "auth_source": row["auth_source"],
            "connection_status": row["connection_status"],
            "credential_status": row["credential_status"],
            "reauth_required": bool(row["reauth_required"]),
            "pull_ready": bool(row["pull_ready"]),
            "status": row["status"],
            "status_reason": row["status_reason"],
            "last_authorized_at": self._dt(row["last_authorized_at"]),
            "last_pull_checked_at": self._dt(row["last_pull_checked_at"]),
            "last_error_at": self._dt(row["last_error_at"]),
        }

    def _compute_pull_ready(
        self,
        *,
        store_active: bool,
        platform: str,
        app_status: str,
        credential_status: str,
        connection_pull_ready: bool,
    ) -> bool:
        return (
            store_active
            and platform in _SUPPORTED_PLATFORMS
            and app_status == "ready"
            and credential_status == "valid"
            and connection_pull_ready
        )

    def _blocked_reasons(
        self,
        *,
        store_active: bool,
        platform: str,
        app_status: str,
        credential_status: str,
        connection_out: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        if not store_active:
            reasons.append("store_inactive")
        if platform not in _SUPPORTED_PLATFORMS:
            reasons.append("unsupported_platform")
        if app_status == "not_configured":
            reasons.append("platform_app_not_ready")
        elif app_status == "ambiguous":
            reasons.append("platform_app_ambiguous")
        elif app_status == "unsupported_platform":
            reasons.append("unsupported_platform")
        if credential_status == "missing":
            reasons.append("credential_missing")
        elif credential_status == "expired":
            reasons.append("credential_expired")
        if not connection_out["pull_ready"]:
            status_reason = connection_out.get("status_reason")
            if status_reason and status_reason not in reasons:
                reasons.append(str(status_reason))
            elif "connection_not_ready" not in reasons:
                reasons.append("connection_not_ready")
        return reasons

    def _latest_job_out(self, row: Mapping | None) -> dict[str, Any] | None:
        if row is None:
            return None

        latest_run = None
        if row["run_id"] is not None:
            latest_run = {
                "id": int(row["run_id"]),
                "status": row["run_status"],
                "page": int(row["run_page"]),
                "page_size": int(row["run_page_size"]),
                "has_more": bool(row["has_more"]),
                "orders_count": int(row["orders_count"]),
                "success_count": int(row["success_count"]),
                "failed_count": int(row["failed_count"]),
                "started_at": self._dt(row["started_at"]),
                "finished_at": self._dt(row["finished_at"]),
                "error_message": row["run_error_message"],
            }

        return {
            "id": int(row["job_id"]),
            "job_type": row["job_type"],
            "status": row["job_status"],
            "time_from": self._dt(row["time_from"]),
            "time_to": self._dt(row["time_to"]),
            "order_status": row["order_status"],
            "page_size": int(row["job_page_size"]),
            "cursor_page": int(row["cursor_page"]),
            "last_run_at": self._dt(row["last_run_at"]),
            "last_success_at": self._dt(row["last_success_at"]),
            "last_error_at": self._dt(row["last_error_at"]),
            "last_error_message": row["last_error_message"],
            "created_at": self._dt(row["job_created_at"]),
            "latest_run": latest_run,
        }

    def _dt(self, value: Any) -> str | None:
        return value.isoformat() if value else None
