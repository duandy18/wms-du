# app/pms/projections/services/pms_projection_service.py
from __future__ import annotations

import os
import time
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import AsyncSessionLocal
from app.integrations.pms.projection_sync import (
    SYNC_VERSION,
    PmsProjectionSyncResult,
    sync_pms_read_projection_once,
)
from app.pms.projections.contracts.pms_projection import ProjectionResource
from app.pms.projections.repos.pms_projection_repo import (
    RESOURCE_ORDER,
    PmsProjectionRepo,
)

SyncCallable = Callable[..., Coroutine[Any, Any, PmsProjectionSyncResult]]


class PmsProjectionService:
    """
    WMS business-domain operations for PMS projection sync.

    Boundary:
    - Reads WMS projection tables and WMS sync-run logs only.
    - Triggers projection_sync, which reads pms-api read-v1 HTTP feed.
    - Does not manage PMS authorization clients or secrets.
    - Must not read or write PMS owner tables.
    """

    def __init__(
        self,
        db: Session,
        *,
        sync_callable: SyncCallable = sync_pms_read_projection_once,
    ) -> None:
        self.db = db
        self.repo = PmsProjectionRepo(db)
        self._sync_callable = sync_callable

    @staticmethod
    def _safe_limit(value: int, *, default: int = 50, max_value: int = 500) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(1, min(number, max_value))

    @staticmethod
    def _safe_offset(value: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = 0
        return max(0, number)

    @staticmethod
    def _pms_api_base_url_snapshot() -> str | None:
        value = (os.getenv("PMS_API_BASE_URL") or "").strip().rstrip("/")
        return value or None

    def get_status(self) -> dict[str, Any]:
        latest_runs = self.repo.latest_sync_runs()
        resources: list[dict[str, Any]] = []

        for resource in RESOURCE_ORDER:
            cfg = self.repo.config(resource)
            stats = self.repo.resource_stats(cfg)
            resources.append(
                {
                    "resource": resource,
                    "table_name": cfg.table_name,
                    "row_count": stats["row_count"],
                    "max_synced_at": stats["max_synced_at"],
                    "last_sync_run": latest_runs.get(resource),
                }
            )

        return {
            "pms_api_base_url_configured": self._pms_api_base_url_snapshot() is not None,
            "resources": resources,
        }

    def _list_projection(
        self,
        *,
        resource: ProjectionResource,
        limit: int,
        offset: int,
        q: str | None = None,
    ) -> dict[str, Any]:
        cfg = self.repo.config(resource)
        safe_limit = self._safe_limit(limit)
        safe_offset = self._safe_offset(offset)

        return self.repo.list_projection_rows(
            cfg=cfg,
            limit=safe_limit,
            offset=safe_offset,
            q=q,
        )

    def list_items(self, *, limit: int, offset: int, q: str | None = None) -> dict[str, Any]:
        return self._list_projection(resource="items", limit=limit, offset=offset, q=q)

    def list_suppliers(self, *, limit: int, offset: int, q: str | None = None) -> dict[str, Any]:
        return self._list_projection(resource="suppliers", limit=limit, offset=offset, q=q)

    def list_uoms(self, *, limit: int, offset: int, q: str | None = None) -> dict[str, Any]:
        return self._list_projection(resource="uoms", limit=limit, offset=offset, q=q)

    def list_sku_codes(self, *, limit: int, offset: int, q: str | None = None) -> dict[str, Any]:
        return self._list_projection(resource="sku-codes", limit=limit, offset=offset, q=q)

    def list_barcodes(self, *, limit: int, offset: int, q: str | None = None) -> dict[str, Any]:
        return self._list_projection(resource="barcodes", limit=limit, offset=offset, q=q)

    async def _sync_resource(
        self,
        *,
        resource: ProjectionResource,
        triggered_by_user_id: int | None,
    ) -> dict[str, Any]:
        self.repo.config(resource)
        started_monotonic = time.monotonic()
        run_id = self.repo.create_sync_run(
            resource=resource,
            triggered_by_user_id=triggered_by_user_id,
            pms_api_base_url_snapshot=self._pms_api_base_url_snapshot(),
            sync_version=SYNC_VERSION,
        )

        try:
            async with AsyncSessionLocal() as async_session:
                result = await self._sync_callable(
                    async_session,
                    resources=[resource],
                )
                await async_session.commit()

            resource_result = result.resources[resource]
            duration_ms = int((time.monotonic() - started_monotonic) * 1000)
            return self.repo.finish_sync_run(
                run_id=run_id,
                status="SUCCESS",
                duration_ms=duration_ms,
                fetched=resource_result.fetched,
                upserted=resource_result.upserted,
                pages=resource_result.pages,
                error_message=None,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - started_monotonic) * 1000)
            self.repo.finish_sync_run(
                run_id=run_id,
                status="FAILED",
                duration_ms=duration_ms,
                error_message=str(exc),
            )
            raise

    async def sync_items(self, *, triggered_by_user_id: int | None) -> dict[str, Any]:
        return await self._sync_resource(
            resource="items",
            triggered_by_user_id=triggered_by_user_id,
        )

    async def sync_suppliers(self, *, triggered_by_user_id: int | None) -> dict[str, Any]:
        return await self._sync_resource(
            resource="suppliers",
            triggered_by_user_id=triggered_by_user_id,
        )

    async def sync_uoms(self, *, triggered_by_user_id: int | None) -> dict[str, Any]:
        return await self._sync_resource(
            resource="uoms",
            triggered_by_user_id=triggered_by_user_id,
        )

    async def sync_sku_codes(self, *, triggered_by_user_id: int | None) -> dict[str, Any]:
        return await self._sync_resource(
            resource="sku-codes",
            triggered_by_user_id=triggered_by_user_id,
        )

    async def sync_barcodes(self, *, triggered_by_user_id: int | None) -> dict[str, Any]:
        return await self._sync_resource(
            resource="barcodes",
            triggered_by_user_id=triggered_by_user_id,
        )

    def list_sync_runs(
        self,
        *,
        resource: ProjectionResource | None,
        limit: int,
    ) -> dict[str, Any]:
        safe_limit = self._safe_limit(limit, default=20, max_value=100)
        if resource is not None:
            self.repo.config(resource)

        return {
            "resource": resource,
            "limit": safe_limit,
            "runs": self.repo.list_sync_runs(resource=resource, limit=safe_limit),
        }

    def _check_projection(
        self,
        *,
        resource: ProjectionResource,
        limit: int = 200,
    ) -> dict[str, Any]:
        self.repo.config(resource)
        safe_limit = self._safe_limit(limit, default=200, max_value=1000)

        if resource == "items":
            rows = self.repo.check_items(safe_limit)
        elif resource == "suppliers":
            rows = self.repo.check_suppliers(safe_limit)
        elif resource == "uoms":
            rows = self.repo.check_uoms(safe_limit)
        elif resource == "sku-codes":
            rows = self.repo.check_sku_codes(safe_limit)
        elif resource == "barcodes":
            rows = self.repo.check_barcodes(safe_limit)
        else:
            raise ValueError("unsupported PMS projection resource: " + str(resource))

        return {
            "resource": resource,
            "ok": len(rows) == 0,
            "issue_count": len(rows),
            "issues": rows,
        }

    def check_items(self, *, limit: int = 200) -> dict[str, Any]:
        return self._check_projection(resource="items", limit=limit)

    def check_suppliers(self, *, limit: int = 200) -> dict[str, Any]:
        return self._check_projection(resource="suppliers", limit=limit)

    def check_uoms(self, *, limit: int = 200) -> dict[str, Any]:
        return self._check_projection(resource="uoms", limit=limit)

    def check_sku_codes(self, *, limit: int = 200) -> dict[str, Any]:
        return self._check_projection(resource="sku-codes", limit=limit)

    def check_barcodes(self, *, limit: int = 200) -> dict[str, Any]:
        return self._check_projection(resource="barcodes", limit=limit)


__all__ = ["PmsProjectionService"]
